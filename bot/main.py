"""GOLD SNIPER - boti live per Railway.

Lidhet me cTrader permes serverit cTrader Trading MCP (URL + Bearer),
lexon qirinjte XAUUSD M15, gjen majat/fundet dhe hap trade. Te shtunen dhe
te dielen (kur ari eshte i mbyllur) tregton BTCUSD me te njejtat module.
Nuk ka nevoje per kompjuter apo per aplikacionin cTrader.
"""
import base64
import dataclasses
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import confluence as conf
from . import hierarchy as hier
from .config import Config
from .data import M15_MS, closed_bars, fetch_bars
from .markets import Market
from .mcp_client import PRICE_SCALE, McpClient, McpError
from .strategy import detect, prepare
from .telegram import Telegram

log = logging.getLogger("gold-sniper")
RECENT_LOGS = deque(maxlen=100)
HIER_NAMES = {"bos": "thyerje strukture M5", "ao": "divergjence AO", "qm": "QM",
              "flip": "zone M5 e thyer", "tl": "trendline M30", "ltf": "zone fresh M15/M30"}


# ---------------------------------------------------------------- helpers
def find_key(obj, *keys):
    """Kerkon celesin e pare qe ekziston (edhe brenda objekteve te brendshme)."""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] is not None:
                return obj[k]
        for v in obj.values():
            r = find_key(v, *keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, *keys)
            if r is not None:
                return r
    return None


def to_price(v):
    """Cmimet vijne here si 4290.5 e here si 429050000 (1/100000)."""
    if v is None:
        return None
    v = float(v)
    return v / PRICE_SCALE if v > 1_000_000 else v


def side_of(pos):
    s = str(find_key(pos, "tradeSide", "side")).upper()
    return "BUY" if s in ("BUY", "1") else "SELL"


DAY_NAMES = {"UP": "TREND LART", "DOWN": "TREND POSHTE", "ROT": "ROTACION"}


def account_env(bearer):
    """DEMO ose LIVE, nga tokeni i cTrader MCP (JSON ne base64url)."""
    try:
        raw = json.loads(base64.urlsafe_b64decode(bearer + "=" * (-len(bearer) % 4)))
        return str(raw.get("environment", "?")).upper()
    except Exception:
        return "?"


def utc(ms=None):
    t = datetime.fromtimestamp((ms or time.time() * 1000) / 1000, timezone.utc)
    return t.strftime("%Y-%m-%d %H:%M UTC")


class RingHandler(logging.Handler):
    def emit(self, record):
        RECENT_LOGS.append(self.format(record))


# ---------------------------------------------------------------- bot
class GoldSniper:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = McpClient(cfg.url, cfg.bearer)
        self.money_digits = 2
        self.deposit_asset = "?"
        self.usd_to_deposit = 1.0
        self.day = None
        self.day_start_balance = None
        self.trades_today = 0
        self.daily_limit_hit = False
        self.last_bar_t = None
        self.last_entry_bar_t = 0
        self.my_position_ids = set()
        self.plans = {}  # positionId -> {"sl", "tp" (None me trailing), "risk", "best"}
        self.adr = None  # ADR e fundit (per trailing stop)
        self.day_kind = ""  # tipi i dites tani: "UP"/"DOWN"/"ROT"/""
        self.last_signal = None
        self.started = utc()
        self.tg = Telegram(cfg.telegram_token, cfg.telegram_chat_id)
        self.env = account_env(cfg.bearer)
        self.day_stats = {"opened": 0, "closed": 0, "wins": 0, "r": 0.0, "pnl": 0.0}
        self.last_balance = self.last_equity = None
        self.open_summary = []   # pozicionet e hapura (per /status)
        # label-i i pozicioneve per cdo modul: sniper, konfluence, hierarki
        self.labels = {"main": cfg.label, "conf": cfg.label + "-C", "hier": cfg.label + "-H"}
        self.conf_base = conf.ConfParams(min_conf=cfg.conf_min_levels, min_rr=cfg.conf_rr)
        self.hier_base = hier.P(min_rr=cfg.hier_rr, min_sl=cfg.hier_min_sl)
        self.conf_params, self.hier_params = self.conf_base, self.hier_base
        self.base = dataclasses.replace(cfg)   # vlerat e arit; per BTC shkallezohen
        self.markets = {}        # symbolId -> Market
        self.mkt = None          # tregu aktual
        self.m5 = []             # qirinjte M5 per modulet e konfluences dhe te hierarkise
        self.last_m5_t = None
        self.error_since = None  # kur filloi problemi i fundit me cTrader
        self.error_sent = 0.0

    # ------------------------------------------------------------ setup
    def setup(self):
        syms = self.client.call("get_symbols").get("symbols", [])
        gold = next((s for s in syms if s.get("symbolName") == self.cfg.symbol_name), None)
        if not gold:
            raise SystemExit("XAUUSD nuk u gjet ne llogari.")
        self.cfg.symbol_id = int(gold["symbolId"])
        c0 = self.base
        gm = Market(c0.symbol_name, self.cfg.symbol_id, c0.lot_size, 1.0, c0.risk_percent, c0.max_lots, "gold",
                    c0.start_hour_utc, c0.end_hour_utc, c0.close_friday_utc)
        self.markets = {gm.symbol_id: gm}
        self.gold = gm
        self.btc = None
        if c0.btc_on:
            b = next((x for x in syms if x.get("symbolName") == c0.btc_symbol), None)
            if b:
                self.btc = Market(c0.btc_symbol, int(b["symbolId"]), 1, c0.btc_scale, c0.btc_risk_percent,
                                  c0.btc_max_lots, "btc", close_sunday_utc=c0.btc_close_sunday_utc)
                self.markets[self.btc.symbol_id] = self.btc
            else:
                log.warning("%s nuk u gjet ne llogari: fundjava pa tregtim", c0.btc_symbol)

        bal = self.client.call("get_balance")
        self.money_digits = int(bal.get("moneyDigits", 2))
        dep_id = bal.get("depositAssetId")
        assets = self.client.call("get_assets").get("assets", [])
        names = {a.get("assetId"): a.get("name") or a.get("displayName") for a in assets}
        self.deposit_asset = names.get(dep_id, "USD") or "USD"
        self._syms = {s.get("symbolName"): s.get("symbolId") for s in syms}
        self.update_conversion()

        log.info("XAUUSD symbolId=%s | Valuta e llogarise: %s | Balanca: %.2f | DRY_RUN=%s",
                 self.cfg.symbol_id, self.deposit_asset, self.balance()[0], self.cfg.dry_run)
        if self.btc:
            log.info("Fundjava: %s (symbolId=%s) e shtune 00:00 - e diel %02d:00 UTC | rreziku %.2f%% | "
                     "vlerat ne $ x%.0f | max %.2f lot", self.btc.name, self.btc.symbol_id, self.btc.close_sunday_utc,
                     self.btc.risk_percent, self.btc.scale, self.btc.max_lots)
        c = self.cfg
        s = c.strategy
        if s.mode == "sniper":
            log.info("Modi SNIPER: lekundje %.2f x ADR | leg min %.2f x ADR | konfirmim %d qirinj | trend %s",
                     s.swing_rev, s.leg_min_adr, s.confirm_bars,
                     f"PO (pullback {s.pull_min_adr:.2f}-{s.pull_max_adr:.2f} x ADR)" if s.trend_entries else "JO")
        else:
            log.info("Modi KLASIK: lookback %d | RSI %g/%g", s.lookback, s.rsi_ob, s.rsi_os)
        exit_txt = f"pa TP, trailing {c.trail_adr:.2f} x ADR pas {c.trail_start_r:.1f}R" if c.trailing else f"TP 1:{c.rr:.1f}"
        log.info("XAUUSD: rreziku %.2f%% | Dalja: %s | BE %.1fR | ora %d-%d UTC",
                 c.risk_percent, exit_txt, c.break_even_r, c.start_hour_utc, c.end_hour_utc)
        if s.mode == "sniper":
            if c.conf_on:
                log.info("Moduli KONFLUENCE: >= %d nivele fresh (me te pakten nje H1/H4) + rejection M5 | TP >= %.1fR",
                         c.conf_min_levels, c.conf_rr)
            if c.hier_on:
                log.info("Moduli HIERARKIA: muri H1 (prekja e pare, pa u thyer) + thyerje strukture M5 + "
                         "divergjence AO + rejection M5 | TP >= %.1fR | SL >= %.1f$", c.hier_rr, c.hier_min_sl)
            log.info("Tipi i dites: TREND kur cmimi >= %.1f x ADR nga hapja (trailing %.1f x ADR%s) | "
                     "ROTACION kur eficienca pas 6 oreve < %.2f (TP %.1f x ADR)",
                     s.trend_day_adr, c.trend_trail_adr, ", mbetet deri ne mbyllje" if c.sticky_trend else "",
                     s.eff_rot, c.rot_tp_adr)
        self.switch_market(self.market_at(datetime.now(timezone.utc)), announce=False)
        bal, eq = self.balance()
        self.last_balance, self.last_equity = bal, eq
        self.tg.send(
            f"🟢 Gold Sniper u nis\n"
            f"Llogaria: {self.env} | Balanca: {bal:,.2f} {self.deposit_asset}\n"
            f"XAUUSD M15 | Rreziku {self.gold.risk_percent}% per trade | Max {self.gold.max_lots} lot\n"
            f"Orari: e hene-e premte {self.gold.start_h:02d}:00-{self.gold.end_h:02d}:00 UTC"
            + (f"\nFundjava: {self.btc.name} (e shtune 00:00 - e diel {self.btc.close_sunday_utc:02d}:00 UTC, "
               f"rreziku {self.btc.risk_percent}%)" if self.btc else "")
            + f"\nTani: {self.mkt.name}"
            + (" | DRY_RUN (pa trade)" if c.dry_run else "")
            + "\nShkruaj /status per gjendjen.")
        self.tg.on_command("/status", self.status_text)
        self.tg.on_command("/start", self.status_text)
        self.tg.on_command("/help", lambda: "Komandat: /status - balanca, pozicioni i hapur, tipi i dites.")
        self.tg.start_commands()

    def update_conversion(self):
        """Sa vlen 1 USD ne valuten e llogarise (per llogaritjen e lotit)."""
        dep = self.deposit_asset
        if dep == "USD":
            self.usd_to_deposit = 1.0
            return
        for name, invert in ((dep + "USD", True), ("USD" + dep, False)):
            sid = self._syms.get(name)
            if sid:
                px = self.client.call("get_spot_prices", {"symbolId": [sid]})["prices"][0]
                mid = (px["bid"] + px["ask"]) / 2 / PRICE_SCALE
                self.usd_to_deposit = 1 / mid if invert else mid
                return
        log.warning("Nuk u gjet kursi USD/%s, perdoret 1.0", dep)

    def balance(self):
        b = self.client.call("get_balance")
        k = 10 ** self.money_digits
        return b["balance"] / k, b.get("equity", b["balance"]) / k

    def spot(self):
        px = self.client.call("get_spot_prices", {"symbolId": [self.cfg.symbol_id]})["prices"][0]
        return px["bid"] / PRICE_SCALE, px["ask"] / PRICE_SCALE

    def market_at(self, dt):
        """BTC ne dritaren e fundjaves (nese eshte aktiv), perndryshe ari."""
        if self.btc and self.btc.in_window(dt):
            return self.btc
        return self.gold

    def market_of(self, pos):
        return self.markets.get(find_key(pos, "symbolId"), self.gold)

    def switch_market(self, m, announce=True):
        """Kalon botin te tregu m: simboli, loti, rreziku dhe vlerat ne $ (x scale)."""
        c, b = self.cfg, self.base
        c.symbol_name, c.symbol_id, c.lot_size = m.name, m.symbol_id, m.lot_size
        c.risk_percent, c.max_lots = m.risk_percent, m.max_lots
        c.min_sl, c.max_sl, c.max_spread = b.min_sl * m.scale, b.max_sl * m.scale, b.max_spread * m.scale
        self.conf_params = conf.scaled(self.conf_base, m.scale)
        self.hier_params = hier.scaled(self.hier_base, m.scale)
        # qirinjte dhe gjendja e simbolit te meparshem s'vlejne me
        self.last_bar_t, self.last_entry_bar_t = None, 0
        self.m5, self.last_m5_t = [], None
        self.adr, self.day_kind, self.last_signal = None, "", None
        old, self.mkt = self.mkt, m
        log.info("Tregu: %s | SL %.2f-%.2f$ | spread max %.2f$ | rreziku %.2f%%", m.name, c.min_sl, c.max_sl,
                 c.max_spread, c.risk_percent)
        if announce and old is not None:
            if m.kind == "btc":
                self.tg.send(f"🔄 Fundjava: ari eshte i mbyllur, boti kalon te {m.name} "
                             f"(rreziku {m.risk_percent}%, deri te dielen {m.close_sunday_utc:02d}:00 UTC).")
            else:
                self.tg.send(f"🔄 Boti kthehet te {m.name} per javen (hyrjet nga {m.start_h:02d}:00 UTC).")

    def my_positions(self):
        data = self.client.call("get_positions")
        out = []
        for p in data.get("positions", []):
            pid = find_key(p, "positionId", "id")
            label = find_key(p, "label")
            comment = find_key(p, "comment")
            sym = find_key(p, "symbolId")
            mine = self.labels.values()
            if pid in self.my_position_ids or label in mine or (comment in mine and sym in self.markets):
                out.append(p)
        return out

    def module_of(self, pos):
        """"main" = moduli sniper, "conf" = konfluenca, "hier" = hierarkia."""
        plan = self.plans.get(find_key(pos, "positionId"))
        if plan and plan.get("module"):
            return plan["module"]
        tags = (find_key(pos, "label"), find_key(pos, "comment"))
        return next((m for m in ("conf", "hier") if self.labels[m] in tags), "main")

    # ------------------------------------------------------------ loop
    def run(self):
        wait = 5
        while True:
            try:
                self.setup()
                break
            except McpError as e:
                log.error("Nisja deshtoi: %s. Provohet perseri pas %ds", e, wait)
                time.sleep(wait)
                wait = min(wait * 2, 120)
        while True:
            try:
                self.tick()
                if self.error_since:
                    mins = (time.time() - self.error_since) / 60
                    if mins >= 5:
                        self.tg.send(f"✅ Lidhja me cTrader u rikthye pas {mins:.0f} minutash.")
                    self.error_since = None
            except McpError as e:
                log.error("Gabim cTrader: %s", e)
                self.notify_error(f"cTrader nuk po pergjigjet: {e}")
            except Exception as e:
                log.exception("Gabim i papritur")
                self.notify_error(f"Gabim i papritur: {e}")
            time.sleep(self.cfg.poll_seconds)

    def notify_error(self, text):
        """Problem qe zgjat: njofto pas 5 minutash, pastaj max 1 here ne 30 minuta."""
        now = time.time()
        self.error_since = self.error_since or now
        if now - self.error_since >= 300 and now - self.error_sent >= 1800:
            self.error_sent = now
            self.tg.send(f"⚠️ {text[:300]}\nBoti vazhdon te provoje vete.")

    def tick(self):
        now = int(time.time() * 1000)
        today = datetime.now(timezone.utc).date()
        if today != self.day:
            if self.day is not None:
                self.send_day_summary(self.day)
            self.day = today
            self.day_start_balance = self.balance()[0]
            self.trades_today = 0
            self.daily_limit_hit = False
            self.update_conversion()
            log.info("Dite e re %s | balanca fillestare %.2f %s", today, self.day_start_balance, self.deposit_asset)

        positions = self.my_positions()
        self.check_closed(positions)
        now_dt = datetime.now(timezone.utc)
        closing = [p for p in positions if self.market_of(p).must_close(now_dt)]
        if closing:
            kinds = {self.market_of(p).kind for p in closing}
            log.info("Mbyllja e tregut (%s): mbyllen %d pozicione", "/".join(sorted(kinds)), len(closing))
            for p in closing:
                self.close(find_key(p, "positionId"), p)
            if "gold" in kinds:
                self.tg.send("🔔 E premte mbremje: pozicionet e arit u mbyllen para fundjaves.")
            if "btc" in kinds:
                self.tg.send("🔔 E diel mbremje: pozicionet BTC u mbyllen. Te henen boti kthehet te ari.")
            positions = self.my_positions()
            self.check_closed(positions)
        want = self.market_at(now_dt)
        if want is not self.mkt:
            self.switch_market(want)
        self.manage(positions)
        self.check_daily_loss(positions)
        if self.cfg.conf_on or self.cfg.hier_on:
            try:
                self.m5_tick(now, positions)
            except McpError as e:
                log.error("Modulet M5: gabim cTrader: %s", e)
        self.open_summary = [
            {"conf": "[K] ", "hier": "[H] "}.get(self.module_of(p), "")
            + f"{side_of(p)} {(find_key(p, 'volume') or 0) / (self.cfg.lot_size * 100):.2f} lot"
            f" @ {to_price(find_key(p, 'price', 'entryPrice', 'openPrice')) or 0:.2f}"
            f" | SL {to_price(find_key(p, 'stopLoss')) or 0:.2f}" for p in positions]

        # prit 5 sekonda pas mbylljes se qirit M15
        if self.last_bar_t is not None and now < self.last_bar_t + 2 * M15_MS + 5000:
            return
        # 16 dite qirinj: 10 dite per ADR + lekundjet e diteve te fundit
        bars = closed_bars(fetch_bars(self.client, self.cfg.symbol_id, now - 16 * 86_400_000, now), now)
        if not bars:
            return
        newest = bars[-1]
        ind = prepare(bars, self.cfg.strategy)
        if "adr" in ind and ind["adr"][-1] == ind["adr"][-1]:
            self.adr = ind["adr"][-1]
        if "day" in ind:
            self.day_kind = ind["day"][-1]
        if self.last_bar_t is None:
            self.last_bar_t = newest.t
            log.info("Boti filloi. Qiri i fundit i mbyllur: %s", utc(newest.t))
            return
        if newest.t <= self.last_bar_t:
            return
        self.last_bar_t = newest.t
        self.on_bar(bars, positions, ind)

    # ------------------------------------------------------------ signals
    def on_bar(self, bars, positions, ind):
        c = self.cfg
        i = len(bars) - 1
        sig = detect(bars, i, c.strategy, ind)
        if not sig:
            return
        if sig.kind == "trend":
            kind = "TREND POSHTE -> SELL pullback" if sig.side == "SELL" else "TREND LART -> BUY pullback"
        else:
            kind = "MAJE -> SELL" if sig.side == "SELL" else "FUND -> BUY"
        self.last_signal = {"time": utc(bars[i].t), "side": sig.side, "extreme": sig.extreme}
        day_txt = DAY_NAMES.get(sig.day, "e paqarte")
        log.info("SINJAL %s | ekstremi %.2f | qiri %s | dita: %s", kind, sig.extreme, utc(bars[i].t), day_txt)

        hour = datetime.now(timezone.utc).hour
        if self.daily_limit_hit:
            return log.info("  injoruar: u arrit humbja max ditore")
        if self.trades_today >= c.max_trades_per_day:
            return log.info("  injoruar: %d trade sot (max)", self.trades_today)
        positions = [q for q in positions if self.module_of(q) == "main"]
        if positions:
            def risk_free(q):
                e, sl = to_price(find_key(q, "price", "entryPrice", "openPrice")), to_price(find_key(q, "stopLoss"))
                return e is not None and sl is not None and (sl >= e if side_of(q) == "BUY" else sl <= e)
            if len(positions) >= c.max_positions or not all(risk_free(q) for q in positions):
                return log.info("  injoruar: ka pozicion te hapur")
        if (bars[i].t - self.last_entry_bar_t) / M15_MS < c.cooldown_bars:
            return log.info("  injoruar: pritje pas trade-it te fundit")
        if not self.mkt.can_open(datetime.now(timezone.utc)):
            return log.info("  injoruar: jashte orarit te %s (%d UTC)", self.mkt.name, hour)

        bid, ask = self.spot()
        if ask - bid > c.max_spread:
            return log.info("  injoruar: spread %.2f > %.2f", ask - bid, c.max_spread)

        entry = ask if sig.side == "BUY" else bid
        risk = max(abs(entry - sig.stop_loss), c.min_sl)
        if risk > c.max_sl:
            return log.info("  injoruar: SL %.2f$ > max %.2f$", risk, c.max_sl)
        if (sig.side == "BUY" and entry <= sig.stop_loss) or (sig.side == "SELL" and entry >= sig.stop_loss):
            return log.info("  injoruar: cmimi ka kaluar tashme SL-ne")

        lots = self.lots_for(risk)
        if lots <= 0:
            return
        tp_dist = None
        if sig.day == "ROT" and c.trailing and c.rot_tp_adr > 0 and self.adr:
            tp_dist = c.rot_tp_adr * self.adr   # dite rotacioni: merr fitimin e rotacionit
        self.open_trade(sig.side, lots, risk, entry, tp_dist, f"{kind} | dita: {day_txt}")
        self.last_entry_bar_t = bars[i].t

    def lots_for(self, risk_price):
        c = self.cfg
        if c.fixed_lots > 0:
            lots = c.fixed_lots
        else:
            balance = self.balance()[0]
            risk_money = balance * c.risk_percent / 100
            loss_per_lot = risk_price * c.lot_size * self.usd_to_deposit  # ne valuten e llogarise
            lots = risk_money / loss_per_lot
        lots = min(lots, c.max_lots)
        lots = int(lots * 100) / 100  # hapi 0.01
        if lots < c.min_lots:
            log.info("  lot i llogaritur %.4f < %.2f -> perdoret %.2f", lots, c.min_lots, c.min_lots)
            lots = c.min_lots
        return lots

    def open_trade(self, side, lots, risk, ref_price, tp_dist=None, note="", module="main", tp_price=None):
        c = self.cfg
        volume = int(round(lots * c.lot_size * 100))
        label = self.labels[module]
        if tp_price is not None:
            tp_dist = abs(tp_price - ref_price)
        if tp_dist is None and not c.trailing:
            tp_dist = risk * c.rr
        log.info("  HAP %s %.2f lot (volume %d) | SL %.2f$ | %s", side, lots, volume, risk,
                 f"TP {tp_dist:.2f}$" if tp_dist else "pa TP (trailing)")
        if c.dry_run:
            log.info("  DRY_RUN: urdhri nuk u dergua")
            if module == "main":
                self.trades_today += 1
            self.tg.send(f"🧪 DRY_RUN: do hapej {side} {lots:.2f} lot @ {ref_price:.2f}\n{note}\n"
                         f"SL {risk:.2f}$ | " + (f"TP {tp_dist:.2f}$" if tp_dist else "trailing"))
            return

        before = {find_key(p, "positionId") for p in self.client.call("get_positions").get("positions", [])}
        # SL/TP relative ne 1/100000 te cmimit (njesia e protokollit cTrader);
        # pas mbushjes vendosen gjithsesi absolute me amend_position.
        args = {
            "symbolId": c.symbol_id, "orderType": "MARKET", "tradeSide": side, "volume": volume,
            "relativeStopLoss": int(round(risk * PRICE_SCALE)),
            "label": label, "comment": label,
        }
        if tp_dist:
            args["relativeTakeProfit"] = int(round(tp_dist * PRICE_SCALE))
        pid, rejected = self.send_market(args, before)
        if pid is None and rejected:
            # serveri e refuzoi -> provo pa SL/TP relative, SL vendoset menjehere me amend
            log.warning("  po provohet urdhri pa SL/TP relative")
            args.pop("relativeStopLoss")
            args.pop("relativeTakeProfit", None)
            pid, _ = self.send_market(args, before)
        if pid is None:
            log.error("  pozicioni nuk u hap")
            self.tg.send(f"⚠️ Sinjal {side} por urdhri nuk u hap. Shiko log-et ne Railway.")
            return

        self.my_position_ids.add(pid)
        if module == "main":
            self.trades_today += 1
        time.sleep(1)
        try:
            details = self.client.call("get_position_details", {"positionId": pid})
        except McpError as e:
            log.error("  get_position_details: %s (perdoret cmimi i references)", e)
            details = {}
        entry = to_price(find_key(details, "price", "entryPrice", "openPrice")) or ref_price
        sl = entry - risk if side == "BUY" else entry + risk
        tp = round(entry + tp_dist if side == "BUY" else entry - tp_dist, 2) if tp_dist else None
        if tp_price is not None:
            tp = round(tp_price, 2)  # konfluenca: TP ne nivelin e zones/trendline-it
        bal_open = self.last_balance
        try:
            bal_open = self.balance()[0]
        except McpError:
            pass
        self.plans[pid] = {"sl": round(sl, 2), "tp": tp, "risk": risk, "best": entry,
                           "side": side, "entry": entry, "lots": lots, "bal_open": bal_open, "lot_size": c.lot_size,
                           "opened": int(time.time() * 1000), "locked_r": 0,
                           "module": module, "fixed": module != "main", "symbol": c.symbol_name}
        self.day_stats["opened"] += 1
        log.info("  U HAP pozicioni %s @ %.2f -> SL %.2f | %s", pid, entry, sl,
                 f"TP {tp:.2f}" if tp else f"pa TP, trailing {c.trail_adr:.2f} x ADR")
        risk_money = risk * lots * c.lot_size * self.usd_to_deposit
        self.tg.send(
            f"🎯 {'🟢 BUY' if side == 'BUY' else '🔴 SELL'} {c.symbol_name} {lots:.2f} lot @ {entry:.2f}\n"
            f"{note}\n"
            f"SL {sl:.2f} ({risk:.2f}$, rrezik ~{risk_money:,.2f} {self.deposit_asset})\n"
            + (f"TP {tp:.2f} (nivel konfluence)" if module == "conf" else
               f"TP {tp:.2f} (niveli fresh perballe)" if module == "hier" else
               f"TP {tp:.2f} (dite rotacioni)" if tp else "Pa TP: trailing stop, e mban deri sa kthehet trendi"))
        self.protect(pid, details)

    def send_market(self, args, before):
        """Dergon urdhrin nje here. Kthen (positionId ose None, refuzuar_nga_serveri)."""
        rejected = False
        try:
            res = self.client.call("create_order", args, retries=1)
            pid = find_key(res, "positionId")
            if pid is not None:
                return pid, False
        except McpError as e:
            rejected = e.rejected
            log.error("  create_order: %s", e)
        # pergjigja nuk kishte positionId ose ra rrjeti -> kontrollo nese u hap gjithsesi
        time.sleep(2)
        for p in self.client.call("get_positions").get("positions", []):
            q = find_key(p, "positionId")
            if q not in before and find_key(p, "symbolId") == self.cfg.symbol_id:
                return q, False
        return None, rejected

    # ------------------------------------------------------------ management
    def protect(self, pid, pos):
        """Siguron qe pozicioni te kete SL/TP te sakte; perndryshe e mbyll."""
        plan = self.plans.get(pid)
        cur_sl = to_price(find_key(pos, "stopLoss"))
        cur_tp = to_price(find_key(pos, "takeProfit"))
        tp_ok = cur_tp is None if plan and plan["tp"] is None else \
            (cur_tp is not None and plan is not None and abs(cur_tp - plan["tp"]) < 0.05)
        if plan and cur_sl is not None and abs(cur_sl - plan["sl"]) < 0.05 and tp_ok:
            plan["ok"] = True
            return
        if plan:
            args = {"positionId": pid, "stopLoss": plan["sl"]}
            if plan["tp"] is not None:
                args["takeProfit"] = plan["tp"]
            try:
                self.client.call("amend_position", args)
                plan["ok"] = True
                log.info("  SL/TP u vendosen per %s: SL %.2f %s", pid, plan["sl"],
                         f"TP {plan['tp']:.2f}" if plan["tp"] else "(pa TP, trailing)")
                return
            except McpError as e:
                log.error("  amend_position deshtoi per %s: %s", pid, e)
        if cur_sl is None:
            log.error("  Pozicioni %s pa SL -> po mbyllet per siguri", pid)
            self.tg.send(f"⚠️ SL nuk u vendos per pozicionin {pid}. U mbyll per siguri.")
            self.close(pid, pos)

    def close(self, pid, pos):
        vol = find_key(pos, "volume")
        if vol is None:
            vol = find_key(self.client.call("get_position_details", {"positionId": pid}), "volume")
        try:
            self.client.call("close_position", {"positionId": pid, "volume": int(vol)}, retries=1)
            log.info("  Pozicioni %s u mbyll", pid)
        except McpError as e:
            log.error("  close_position deshtoi per %s: %s", pid, e)

    def manage(self, positions):
        for pos in positions:
            pid = find_key(pos, "positionId")
            plan = self.plans.get(pid)
            if (plan is not None and not plan.get("ok")) or find_key(pos, "stopLoss") is None:
                self.protect(pid, pos)
                continue
            if self.market_of(pos) is not self.mkt:
                continue          # pozicion i tregut tjeter: mbrohet vetem me SL/TP (mbyllet ne kufi)
            module = self.module_of(pos)
            if module != "main":
                # konfluenca/hierarkia: SL dhe TP fikse, pa break-even/trailing (si ne backtest)
                if plan is None:
                    entry = to_price(find_key(pos, "price", "entryPrice", "openPrice")) or 0
                    sl = to_price(find_key(pos, "stopLoss")) or entry
                    self.plans[pid] = {"sl": sl, "tp": to_price(find_key(pos, "takeProfit")),
                                       "risk": abs(entry - sl) or 1.0, "best": entry, "ok": True,
                                       "side": side_of(pos), "entry": entry,
                                       "lots": (find_key(pos, "volume") or 0) / (self.cfg.lot_size * 100),
                                       "bal_open": self.last_balance, "opened": int(time.time() * 1000),
                                       "module": module, "fixed": True, "symbol": self.mkt.name,
                                       "lot_size": self.cfg.lot_size}
                continue
            self.manage_stop(pid, pos, plan)

    # ------------------------------------------------------------ modulet M5
    def m5_tick(self, now, positions):
        """Cdo 5 minuta: qirinjte M5 te 12 diteve te fundit -> konfluenca dhe hierarkia."""
        c = self.cfg
        if self.last_m5_t is not None and now < self.last_m5_t + 2 * conf.TF["M5"] + 5000:
            return
        # 12 dite M5 heren e pare; pastaj vetem oret e fundit
        since = now - 12 * 86_400_000 if not self.m5 else self.m5[-1].t - 3_600_000
        fresh = fetch_bars(self.client, c.symbol_id, since, now, "M_5")
        merged = {b.t: b for b in self.m5}
        merged.update({b.t: b for b in fresh})
        self.m5 = [merged[k] for k in sorted(merged) if k >= now - 12 * 86_400_000 and k + conf.TF["M5"] <= now]
        if not self.m5:
            return
        newest = self.m5[-1]
        if self.last_m5_t is None or newest.t <= self.last_m5_t:
            self.last_m5_t = self.last_m5_t or newest.t
            return
        self.last_m5_t = newest.t
        if c.conf_on:
            p = self.conf_params
            ind = conf.prepare(self.m5, p)
            sig = conf.evaluate(newest, ind["adr"][-1], conf.active_zones(ind["zones"], newest, p), ind["lines"], p)
            if sig:
                levels = "+".join(sig["levels"])
                log.info("KONFLUENCE %s | nivele %s | SL %.2f TP %.2f | qiri %s", sig["side"], levels,
                         sig["sl"], sig["tp"], utc(newest.t))
                self.fixed_trade("conf", sig, p.min_rr, p.min_sl, p.max_sl, now, positions,
                                 f"KONFLUENCE: {levels} + rejection M5")
        if c.hier_on:
            p = self.hier_params
            sig = hier.signal(self.m5, p)
            if sig:
                extra = [HIER_NAMES[f] for f in sig["feats"] if f not in p.need]
                log.info("HIERARKIA %s | muri %s | %s | SL %.2f TP %.2f | qiri %s", sig["side"], sig["htf"],
                         "+".join(sig["feats"]), sig["sl"], sig["tp"], utc(newest.t))
                self.fixed_trade("hier", sig, p.min_rr, p.min_sl, p.max_sl, now, positions,
                                 f"HIERARKIA: muri {sig['htf']} s'u thye + thyerje strukture M5 + divergjence AO"
                                 + (f" + {', '.join(extra)}" if extra else "") + " + rejection M5")

    def fixed_trade(self, module, sig, min_rr, min_sl, max_sl, now, positions, note):
        """Trade me SL/TP fikse per modulet M5 (nje pozicion per modul)."""
        c = self.cfg
        if self.daily_limit_hit:
            return log.info("  injoruar: u arrit humbja max ditore")
        if any(self.module_of(q) == module for q in positions):
            return log.info("  injoruar: moduli ka pozicion te hapur")
        if not self.mkt.can_open(datetime.fromtimestamp(now / 1000, timezone.utc)):
            return log.info("  injoruar: jashte orarit te %s", self.mkt.name)
        bid, ask = self.spot()
        if ask - bid > c.max_spread:
            return log.info("  injoruar: spread %.2f", ask - bid)
        buy = sig["side"] == "BUY"
        entry = ask if buy else bid
        if (buy and entry <= sig["sl"]) or (not buy and entry >= sig["sl"]):
            return log.info("  injoruar: cmimi ka kaluar SL-ne")
        risk = max(abs(entry - sig["sl"]), min_sl)
        if risk > max_sl or abs(sig["tp"] - entry) < min_rr * risk or (buy and sig["tp"] <= entry) or (
                not buy and sig["tp"] >= entry):
            return log.info("  injoruar: SL %.2f$ ose TP me pak se %.1fR", risk, min_rr)
        lots = self.lots_for(risk)
        if lots > 0:
            self.open_trade(sig["side"], lots, risk, entry, note=note, module=module, tp_price=sig["tp"])

    def manage_stop(self, pid, pos, plan):
        """Break-even dhe trailing stop: SL ndjek cmimin me distance trail_adr x ADR
        pasi fitimi arrin trail_start_r x rrezikun fillestar."""
        c = self.cfg
        entry = to_price(find_key(pos, "price", "entryPrice", "openPrice"))
        sl = to_price(find_key(pos, "stopLoss"))
        if entry is None or sl is None:
            return
        buy = side_of(pos) == "BUY"
        if plan is None:
            # pozicion nga para rinisjes: rreziku = distanca e SL (nese ende ne humbje)
            risk = entry - sl if buy else sl - entry
            if risk <= 0:
                risk = abs(entry - sl) or c.min_sl
            plan = self.plans[pid] = {"sl": sl, "tp": None, "risk": risk, "best": entry, "ok": True,
                                      "side": "BUY" if buy else "SELL", "entry": entry,
                                      "lots": (find_key(pos, "volume") or 0) / (c.lot_size * 100),
                                      "bal_open": self.last_balance, "opened": int(time.time() * 1000),
                                      "locked_r": 0, "symbol": self.mkt.name, "lot_size": c.lot_size}
        bid, ask = self.spot()
        price = bid if buy else ask
        plan["best"] = max(plan["best"], price) if buy else min(plan["best"], price)
        fav = plan["best"] - entry if buy else entry - plan["best"]
        risk = plan["risk"]

        new_sl = sl
        if c.break_even_r > 0 and fav >= risk * c.break_even_r:
            buf = max(ask - bid, 0.05)
            be = entry + buf if buy else entry - buf
            new_sl = max(new_sl, be) if buy else min(new_sl, be)
        if c.trailing and self.adr and fav >= risk * c.trail_start_r:
            # dite trendi ne drejtimin e trade-it -> jepi me shume hapesire; pasi trade-i njihet
            # si trend mbetet i tille, qe nje rikthim te mos e ngushtoje trailing-un
            with_trend = self.day_kind == ("UP" if buy else "DOWN")
            if c.sticky_trend:
                plan["wide"] = plan.get("wide", False) or with_trend
                with_trend = with_trend or plan["wide"]
            dist = (c.trend_trail_adr if with_trend and c.trend_trail_adr > 0 else c.trail_adr) * self.adr
            trail = plan["best"] - dist if buy else plan["best"] + dist
            new_sl = max(new_sl, trail) if buy else min(new_sl, trail)
        new_sl = round(new_sl, 2)
        # levize vetem kur SL permiresohet te pakten 0.5$ (x scale per BTC; pa spam urdhrash)
        if (new_sl - sl if buy else sl - new_sl) >= 0.5 * self.mkt.scale:
            self.client.call("amend_position", {"positionId": pid, "stopLoss": new_sl})
            plan["sl"] = new_sl
            log.info("SL i %s u zhvendos ne %.2f (fitimi max %.2f$ = %.1fR)", pid, new_sl, fav, fav / risk)
            locked = (new_sl - entry if buy else entry - new_sl) / risk
            if locked >= 0 and plan.get("locked_r", 0) < 0.001 and not plan.get("be_sent"):
                plan["be_sent"] = True
                self.tg.send(f"🔒 {plan.get('side', '')} @ {entry:.2f}: SL ne hyrje ({new_sl:.2f}). Trade-i s'humbet me.")
            if locked >= plan.get("locked_r", 0) + 2:
                plan["locked_r"] = int(locked)
                self.tg.send(f"📈 {plan.get('side', '')} @ {entry:.2f}: SL ne {new_sl:.2f}, "
                             f"fitim i siguruar +{locked:.1f}R. Vazhdon ta kaleroje.")

    def check_daily_loss(self, positions):
        if self.daily_limit_hit or not self.day_start_balance:
            return
        bal, equity = self.balance()
        self.last_balance, self.last_equity = bal, equity
        loss_pct = (self.day_start_balance - equity) / self.day_start_balance * 100
        if loss_pct >= self.cfg.max_daily_loss_pct:
            self.daily_limit_hit = True
            log.warning("Humbja ditore %.2f%% >= %.2f%% -> mbyllen pozicionet, s'tregtohet me sot",
                        loss_pct, self.cfg.max_daily_loss_pct)
            self.tg.send(f"🛑 Humbja e sotme {loss_pct:.2f}% arriti kufirin {self.cfg.max_daily_loss_pct}%. "
                         f"Pozicionet u mbyllen, boti s'tregton me sot.")
            for p in positions:
                self.close(find_key(p, "positionId"), p)

    # ------------------------------------------------------------ njoftime
    def check_closed(self, positions):
        """Pozicionet e botit qe s'jane me te hapura -> njofto rezultatin."""
        open_ids = {find_key(p, "positionId") for p in positions}
        for pid in [q for q in self.plans if q not in open_ids]:
            plan = self.plans.pop(pid)
            self.my_position_ids.discard(pid)
            try:
                self.report_close(pid, plan)
            except Exception as e:
                log.warning("Raporti i mbylljes per %s: %s", pid, e)

    def exit_price(self, pid, plan):
        """Cmimi i mbylljes nga deal-et e pozicionit; perndryshe SL/TP i fundit."""
        opp = "SELL" if plan.get("side") == "BUY" else "BUY"
        deals = []
        try:
            d = self.client.call("get_position_details", {"positionId": pid})
            deals = find_key(d, "deals") or []
        except McpError:
            pass
        if not deals:
            try:
                now = int(time.time() * 1000)
                d = self.client.call("get_deals", {"fromTimestamp": str(plan.get("opened", now) - 3_600_000),
                                                   "toTimestamp": str(now), "maxRows": 200})
                deals = [x for x in d.get("deals", []) if x.get("positionId") == pid]
            except McpError:
                pass
        closing = [x for x in deals if str(x.get("tradeSide", "")).upper() == opp and x.get("executionPrice")]
        if closing:
            last = max(closing, key=lambda x: x.get("executionTimestamp", 0))
            return to_price(last["executionPrice"]), True
        return (plan.get("tp") or plan.get("sl")), False

    def report_close(self, pid, plan):
        px, exact = self.exit_price(pid, plan)
        entry, risk, buy = plan.get("entry"), plan.get("risk") or 1, plan.get("side") == "BUY"
        r = ((px - entry) if buy else (entry - px)) / risk if px and entry else 0.0
        bal, eq = self.balance()
        self.last_balance, self.last_equity = bal, eq
        # fitimi nga cmimet e ketij pozicioni (ndryshimi i balances perzihet kur mbyllen disa pozicione njeheresh)
        lot_size = plan.get("lot_size") or self.markets.get(plan.get("symbol_id"), self.gold).lot_size
        pnl = ((px - entry) if buy else (entry - px)) * plan.get("lots", 0) * lot_size * self.usd_to_deposit \
            if px and entry else None
        self.day_stats["closed"] += 1
        self.day_stats["r"] += r
        self.day_stats["wins"] += r > 0.05
        if pnl is not None:
            self.day_stats["pnl"] += pnl
        icon = "✅" if r > 0.05 else ("➖" if r > -0.05 else "❌")
        hours = (time.time() * 1000 - plan.get("opened", time.time() * 1000)) / 3_600_000
        self.tg.send(
            f"{icon} U mbyll {plan.get('side', '')} {plan.get('symbol', '')} {plan.get('lots', 0):.2f} lot\n"
            f"Hyrja {entry:.2f} -> dalja {px:.2f}{'' if exact else ' (afersisht)'} | {r:+.1f}R | {hours:.1f} ore\n"
            + (f"Fitimi: {pnl:+,.2f} {self.deposit_asset} (pa komision)\n" if pnl is not None else "")
            + f"Balanca: {bal:,.2f} {self.deposit_asset}")
        log.info("Pozicioni %s u mbyll @ %.2f | %+.1fR | %s", pid, px or 0, r,
                 f"{pnl:+.2f} {self.deposit_asset}" if pnl is not None else "")

    def send_day_summary(self, day):
        st = self.day_stats
        self.day_stats = {"opened": 0, "closed": 0, "wins": 0, "r": 0.0, "pnl": 0.0}
        if st["opened"] == 0 and st["closed"] == 0:
            return
        bal = self.last_balance
        change = ((bal - self.day_start_balance) / self.day_start_balance * 100
                  if bal and self.day_start_balance else None)
        self.tg.send(
            f"📊 Permbledhja e dites {day}\n"
            f"Trade te hapura: {st['opened']} | te mbyllura: {st['closed']} (fitime {st['wins']})\n"
            f"Rezultati: {st['r']:+.1f}R | {st['pnl']:+,.2f} {self.deposit_asset}"
            + (f" ({change:+.2f}%)" if change is not None else "")
            + (f"\nBalanca: {bal:,.2f} {self.deposit_asset}" if bal else ""))

    def status_text(self):
        c = self.cfg
        lines = [f"📍 Gold Sniper | {self.env}" + (" | DRY_RUN" if c.dry_run else "")]
        if self.last_balance is not None:
            lines.append(f"Balanca: {self.last_balance:,.2f} {self.deposit_asset} | "
                         f"Equity: {self.last_equity:,.2f}")
        lines.append(f"Dita: {DAY_NAMES.get(self.day_kind, 'e paqarte')}"
                     + (f" | ADR {self.adr:.0f}$" if self.adr else ""))
        lines.append(f"Sot: {self.day_stats['opened']} trade, {self.day_stats['r']:+.1f}R"
                     + (" | 🛑 limiti ditor u arrit" if self.daily_limit_hit else ""))
        lines.append("Pozicione: " + ("; ".join(self.open_summary) if self.open_summary else "asnje"))
        if self.last_signal:
            lines.append(f"Sinjali i fundit: {self.last_signal['side']} @ {self.last_signal['extreme']:.2f} "
                         f"({self.last_signal['time']})")
        m = self.mkt
        if m:
            win = (f"e shtune 00:00 - e diel {m.close_sunday_utc:02d}:00 UTC" if m.kind == "btc"
                   else f"e hene-e premte {m.start_h:02d}-{m.end_h:02d} UTC")
            lines.append(f"Tregu: {m.name} | orari: {'brenda' if m.can_open(datetime.now(timezone.utc)) else 'jashte'}"
                         f" ({win})")
        return "\n".join(lines)

    def status(self):
        return {
            "bot": "Gold Sniper XAUUSD M15",
            "started": self.started,
            "dry_run": self.cfg.dry_run,
            "last_closed_bar": utc(self.last_bar_t) if self.last_bar_t else None,
            "trades_today": self.trades_today,
            "daily_limit_hit": self.daily_limit_hit,
            "last_signal": self.last_signal,
            "logs": list(RECENT_LOGS)[-40:],
        }


# ---------------------------------------------------------------- status web
def start_status_server(bot: GoldSniper):
    port = os.environ.get("PORT")
    if not port:
        return

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(bot.status(), indent=2, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("0.0.0.0", int(port)), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("Faqja e statusit ne portin %s", port)


def main():
    fmt = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, stream=sys.stdout)  # Railway: stderr shfaqet si [error]
    ring = RingHandler()
    ring.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(ring)

    bot = GoldSniper(Config.from_env())
    start_status_server(bot)
    bot.run()


if __name__ == "__main__":
    main()
