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
from bot.strategy import atr_series, rsi_series, detect


def run(bars, cfg: Config, verbose=True):
    p = cfg.strategy
    atr = atr_series(bars, p.atr_period)
    rsi = rsi_series(bars, p.rsi_period)
    trades = []
    pos = None
    last_entry_i = -10_000
    spread = cfg.backtest_spread

    for i in range(len(bars)):
        b = bars[i]
        # ---- menaxho pozicionin e hapur ne qirin i ----
        if pos:
            side, entry, sl, tp, risk, be_done = pos["side"], pos["entry"], pos["sl"], pos["tp"], pos["risk"], pos["be"]
            if side == "BUY":
                hit_sl, hit_tp = b.l <= sl, b.h >= tp
                fav = b.h - entry
            else:
                hit_sl, hit_tp = b.h + spread >= sl, b.l + spread <= tp
                fav = entry - (b.l + spread)
            exit_px = None
            if hit_sl:              # konservative: SL para TP ne te njejtin qiri
                exit_px = sl
            elif hit_tp:
                exit_px = tp
            if exit_px is not None:
                r = ((exit_px - entry) if side == "BUY" else (entry - exit_px)) / risk
                pos["exit"], pos["r"], pos["exit_t"] = exit_px, r, b.t
                trades.append(pos)
                pos = None
            elif cfg.break_even_r > 0 and not be_done and fav >= risk * cfg.break_even_r:
                pos["sl"] = entry + (spread if side == "BUY" else -spread)
                pos["be"] = True

        # ---- sinjal ne mbyllje te qirit i -> hyrje ne hapje te i+1 ----
        if pos is None and i + 1 < len(bars) and i - last_entry_i >= cfg.cooldown_bars:
            hour = datetime.fromtimestamp(bars[i + 1].t / 1000, timezone.utc).hour
            if not cfg.in_session(hour):
                continue
            sig = detect(bars, i, p, atr, rsi)
            if not sig:
                continue
            nb = bars[i + 1]
            entry = nb.o + spread if sig.side == "BUY" else nb.o
            risk = abs(entry - sig.stop_loss)
            risk = max(risk, cfg.min_sl)
            if risk > cfg.max_sl:
                continue
            sl = entry - risk if sig.side == "BUY" else entry + risk
            tp = entry + risk * cfg.rr if sig.side == "BUY" else entry - risk * cfg.rr
            pos = {"side": sig.side, "entry": entry, "sl": sl, "tp": tp, "risk": risk,
                   "be": False, "t": nb.t, "extreme": sig.extreme}
            last_entry_i = i

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
