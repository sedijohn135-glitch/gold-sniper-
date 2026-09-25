"""GOLD SNIPER - boti live per Railway.

Lidhet me cTrader permes serverit cTrader Trading MCP (URL + Bearer),
lexon qirinjte XAUUSD M15, gjen majat/fundet dhe hap trade.
Nuk ka nevoje per kompjuter apo per aplikacionin cTrader.
"""
import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .data import M15_MS, closed_bars, fetch_bars
from .mcp_client import PRICE_SCALE, McpClient, McpError
from .strategy import detect

log = logging.getLogger("gold-sniper")
RECENT_LOGS = deque(maxlen=100)


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
        self.plans = {}  # positionId -> {"sl":..., "tp":...}
        self.last_signal = None
        self.started = utc()

    # ------------------------------------------------------------ setup
    def setup(self):
        syms = self.client.call("get_symbols").get("symbols", [])
        gold = next((s for s in syms if s.get("symbolName") == self.cfg.symbol_name), None)
        if not gold:
            raise SystemExit("XAUUSD nuk u gjet ne llogari.")
        self.cfg.symbol_id = int(gold["symbolId"])

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
        c = self.cfg
        s = c.strategy
        if s.mode == "sniper":
            log.info("Modi SNIPER: lekundje %.2f x ADR | leg min %.2f x ADR | konfirmim %d qirinj",
                     s.swing_rev, s.leg_min_adr, s.confirm_bars)
        else:
            log.info("Modi KLASIK: lookback %d | RSI %g/%g", s.lookback, s.rsi_ob, s.rsi_os)
        log.info("Rreziku %.2f%% | RR 1:%.1f | BE %.1fR | ora %d-%d UTC",
                 c.risk_percent, c.rr, c.break_even_r, c.start_hour_utc, c.end_hour_utc)

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

    def my_positions(self):
        data = self.client.call("get_positions")
        out = []
        for p in data.get("positions", []):
            pid = find_key(p, "positionId", "id")
            label = find_key(p, "label")
            comment = find_key(p, "comment")
            sym = find_key(p, "symbolId")
            if pid in self.my_position_ids or label == self.cfg.label or (
                    comment == self.cfg.label and sym == self.cfg.symbol_id):
                out.append(p)
        return out

    # ------------------------------------------------------------ loop
    def run(self):
        self.setup()
        while True:
            try:
                self.tick()
            except McpError as e:
                log.error("Gabim cTrader: %s", e)
            except Exception:
                log.exception("Gabim i papritur")
            time.sleep(self.cfg.poll_seconds)

    def tick(self):
        now = int(time.time() * 1000)
        today = datetime.now(timezone.utc).date()
        if today != self.day:
            self.day = today
            self.day_start_balance = self.balance()[0]
            self.trades_today = 0
            self.daily_limit_hit = False
            self.update_conversion()
            log.info("Dite e re %s | balanca fillestare %.2f %s", today, self.day_start_balance, self.deposit_asset)

        positions = self.my_positions()
        self.manage(positions)
        self.check_daily_loss(positions)

        # prit 5 sekonda pas mbylljes se qirit M15
        if self.last_bar_t is not None and now < self.last_bar_t + 2 * M15_MS + 5000:
            return
        # 16 dite qirinj: 10 dite per ADR + lekundjet e diteve te fundit
        bars = closed_bars(fetch_bars(self.client, self.cfg.symbol_id, now - 16 * 86_400_000, now), now)
        if not bars:
            return
        newest = bars[-1]
        if self.last_bar_t is None:
            self.last_bar_t = newest.t
            log.info("Boti filloi. Qiri i fundit i mbyllur: %s", utc(newest.t))
            return
        if newest.t <= self.last_bar_t:
            return
        self.last_bar_t = newest.t
        self.on_bar(bars, positions)

    # ------------------------------------------------------------ signals
    def on_bar(self, bars, positions):
        c = self.cfg
        i = len(bars) - 1
        sig = detect(bars, i, c.strategy)
        if not sig:
            return
        kind = "MAJE -> SELL" if sig.side == "SELL" else "FUND -> BUY"
        self.last_signal = {"time": utc(bars[i].t), "side": sig.side, "extreme": sig.extreme}
        log.info("SINJAL %s | ekstremi %.2f | qiri %s", kind, sig.extreme, utc(bars[i].t))

        hour = datetime.now(timezone.utc).hour
        if self.daily_limit_hit:
            return log.info("  injoruar: u arrit humbja max ditore")
        if self.trades_today >= c.max_trades_per_day:
            return log.info("  injoruar: %d trade sot (max)", self.trades_today)
        if positions:
            return log.info("  injoruar: ka pozicion te hapur")
        if (bars[i].t - self.last_entry_bar_t) / M15_MS < c.cooldown_bars:
            return log.info("  injoruar: pritje pas trade-it te fundit")
        if not c.in_session(hour):
            return log.info("  injoruar: jashte orarit (%d UTC)", hour)

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
        self.open_trade(sig.side, lots, risk, entry)
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

    def open_trade(self, side, lots, risk, ref_price):
        c = self.cfg
        volume = int(round(lots * c.lot_size * 100))
        log.info("  HAP %s %.2f lot (volume %d) | SL %.2f$ | TP %.2f$", side, lots, volume, risk, risk * c.rr)
        if c.dry_run:
            log.info("  DRY_RUN: urdhri nuk u dergua")
            self.trades_today += 1
            return

        before = {find_key(p, "positionId") for p in self.client.call("get_positions").get("positions", [])}
        # SL/TP relative ne 1/100000 te cmimit (njesia e protokollit cTrader);
        # pas mbushjes vendosen gjithsesi absolute me amend_position.
        args = {
            "symbolId": c.symbol_id, "orderType": "MARKET", "tradeSide": side, "volume": volume,
            "relativeStopLoss": int(round(risk * PRICE_SCALE)),
            "relativeTakeProfit": int(round(risk * c.rr * PRICE_SCALE)),
            "label": c.label, "comment": c.label,
        }
        pid, rejected = self.send_market(args, before)
        if pid is None and rejected:
            # serveri e refuzoi -> provo pa SL/TP relative, SL vendoset menjehere me amend
            log.warning("  po provohet urdhri pa SL/TP relative")
            args.pop("relativeStopLoss")
            args.pop("relativeTakeProfit")
            pid, _ = self.send_market(args, before)
        if pid is None:
            log.error("  pozicioni nuk u hap")
            return

        self.my_position_ids.add(pid)
        self.trades_today += 1
        time.sleep(1)
        try:
            details = self.client.call("get_position_details", {"positionId": pid})
        except McpError as e:
            log.error("  get_position_details: %s (perdoret cmimi i references)", e)
            details = {}
        entry = to_price(find_key(details, "price", "entryPrice", "openPrice")) or ref_price
        sl = entry - risk if side == "BUY" else entry + risk
        tp = entry + risk * c.rr if side == "BUY" else entry - risk * c.rr
        self.plans[pid] = {"sl": round(sl, 2), "tp": round(tp, 2)}
        log.info("  U HAP pozicioni %s @ %.2f -> SL %.2f | TP %.2f", pid, entry, sl, tp)
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
        if plan and cur_sl is not None and abs(cur_sl - plan["sl"]) < 0.05 and \
                cur_tp is not None and abs(cur_tp - plan["tp"]) < 0.05:
            plan["ok"] = True
            return
        if plan:
            try:
                self.client.call("amend_position", {"positionId": pid, "stopLoss": plan["sl"],
                                                     "takeProfit": plan["tp"]})
                plan["ok"] = True
                log.info("  SL/TP u vendosen per %s: SL %.2f TP %.2f", pid, plan["sl"], plan["tp"])
                return
            except McpError as e:
                log.error("  amend_position deshtoi per %s: %s", pid, e)
        if cur_sl is None:
            log.error("  Pozicioni %s pa SL -> po mbyllet per siguri", pid)
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
            self.break_even(pid, pos)

    def break_even(self, pid, pos):
        c = self.cfg
        if c.break_even_r <= 0:
            return
        entry = to_price(find_key(pos, "price", "entryPrice", "openPrice"))
        sl = to_price(find_key(pos, "stopLoss"))
        if entry is None or sl is None:
            return
        side = side_of(pos)
        risk = entry - sl if side == "BUY" else sl - entry
        if risk <= 0:  # tashme ne break-even
            return
        bid, ask = self.spot()
        price = bid if side == "BUY" else ask
        profit = price - entry if side == "BUY" else entry - price
        if profit >= risk * c.break_even_r:
            buf = max(ask - bid, 0.05)
            new_sl = round(entry + buf if side == "BUY" else entry - buf, 2)
            self.client.call("amend_position", {"positionId": pid, "stopLoss": new_sl})
            log.info("Break-even: SL i %s u zhvendos ne %.2f", pid, new_sl)

    def check_daily_loss(self, positions):
        if self.daily_limit_hit or not self.day_start_balance:
            return
        _, equity = self.balance()
        loss_pct = (self.day_start_balance - equity) / self.day_start_balance * 100
        if loss_pct >= self.cfg.max_daily_loss_pct:
            self.daily_limit_hit = True
            log.warning("Humbja ditore %.2f%% >= %.2f%% -> mbyllen pozicionet, s'tregtohet me sot",
                        loss_pct, self.cfg.max_daily_loss_pct)
            for p in positions:
                self.close(find_key(p, "positionId"), p)

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
    logging.basicConfig(level=logging.INFO, format=fmt)
    ring = RingHandler()
    ring.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(ring)

    bot = GoldSniper(Config.from_env())
    start_status_server(bot)
    bot.run()


if __name__ == "__main__":
    main()
