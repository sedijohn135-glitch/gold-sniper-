"""Backtest i thjeshte i strategjise me te dhenat reale nga cTrader.

Perdorimi:  python backtest.py [dite=60]
Kerkon variablat URL dhe Bearer (si boti).
"""
import sys
import time
from datetime import datetime, timezone

from bot.config import Config
from bot.mcp_client import McpClient
from bot.data import fetch_bars
from bot.strategy import detect, prepare


def run(bars, cfg: Config, verbose=True):
    p = cfg.strategy
    ind = prepare(bars, p)
    trades = []
    open_pos = []
    last_entry_i = -10_000
    per_day = {}
    spread = cfg.backtest_spread

    for i in range(len(bars)):
        b = bars[i]
        # ---- menaxho pozicionin e hapur ne qirin i ----
        for pos in list(open_pos):
            buy = pos["side"] == "BUY"
            entry, risk, tp = pos["entry"], pos["risk"], pos["tp"]
            lo, hi = (b.l, b.h) if buy else (b.l + spread, b.h + spread)
            exit_px = None
            if (buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"]):
                exit_px = pos["sl"]      # konservative: SL para TP ne te njejtin qiri
            elif tp is not None and ((buy and hi >= tp) or (not buy and lo <= tp)):
                exit_px = tp
            if exit_px is not None:
                pos["exit"], pos["exit_t"] = exit_px, b.t
                pos["r"] = ((exit_px - entry) if buy else (entry - exit_px)) / risk
                trades.append(pos)
                open_pos.remove(pos)
            else:
                pos["best"] = max(pos["best"], hi) if buy else min(pos["best"], lo)
                fav = pos["best"] - entry if buy else entry - pos["best"]
                new_sl = pos["sl"]
                if cfg.break_even_r > 0 and fav >= risk * cfg.break_even_r:
                    be = entry + spread if buy else entry - spread
                    new_sl = max(new_sl, be) if buy else min(new_sl, be)
                if cfg.trailing and fav >= risk * cfg.trail_start_r and ind["adr"][i] == ind["adr"][i]:
                    d = cfg.trail_adr * ind["adr"][i]
                    new_sl = max(new_sl, pos["best"] - d) if buy else min(new_sl, pos["best"] + d)
                pos["sl"] = new_sl

        # ---- sinjal ne mbyllje te qirit i -> hyrje ne hapje te i+1 ----
        # pozicion i ri: kur s'ka asnje, ose kur te gjithe te hapurit jane pa rrezik (SL >= hyrja)
        free = all((q["sl"] >= q["entry"]) if q["side"] == "BUY" else (q["sl"] <= q["entry"]) for q in open_pos)
        if len(open_pos) < cfg.max_positions and free and i + 1 < len(bars) and i - last_entry_i >= cfg.cooldown_bars:
            nt = datetime.fromtimestamp(bars[i + 1].t / 1000, timezone.utc)
            if not cfg.in_session(nt.hour) or per_day.get(nt.date(), 0) >= cfg.max_trades_per_day:
                continue
            sig = detect(bars, i, p, ind)
            if not sig:
                continue
            nb = bars[i + 1]
            entry = nb.o + spread if sig.side == "BUY" else nb.o
            risk = abs(entry - sig.stop_loss)
            risk = max(risk, cfg.min_sl)
            if risk > cfg.max_sl:
                continue
            sl = entry - risk if sig.side == "BUY" else entry + risk
            tp = None if cfg.trailing else (entry + risk * cfg.rr if sig.side == "BUY" else entry - risk * cfg.rr)
            open_pos.append({"side": sig.side, "entry": entry, "sl": sl, "tp": tp, "risk": risk,
                             "best": entry, "t": nb.t, "extreme": sig.extreme})
            last_entry_i = i
            per_day[nt.date()] = per_day.get(nt.date(), 0) + 1

    if verbose:
        for t in trades:
            ts = datetime.fromtimestamp(t["t"] / 1000, timezone.utc).strftime("%m-%d %H:%M")
            print(f"{ts} UTC {t['side']:4} @ {t['entry']:.2f} ekstremi {t['extreme']:.2f} "
                  f"SL {t['risk']:.2f}$ -> {t['r']:+.2f}R")
    wins = [t for t in trades if t["r"] > 0.05]
    losses = [t for t in trades if t["r"] < -0.05]
    total_r = sum(t["r"] for t in trades)
    print(f"\nTrade: {len(trades)} | Fitime: {len(wins)} | Humbje: {len(losses)} | "
          f"Break-even: {len(trades) - len(wins) - len(losses)} | Totali: {total_r:+.2f}R")
    return trades, total_r


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    cfg = Config.from_env()
    client = McpClient(cfg.url, cfg.bearer)
    now = int(time.time() * 1000)
    bars = fetch_bars(client, cfg.symbol_id, now - days * 86_400_000, now)
    print(f"{len(bars)} qirinj M15 XAUUSD ({days} dite)\n")
    run(bars, cfg)
