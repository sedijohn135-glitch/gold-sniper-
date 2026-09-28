"""Backtest i modulit live ZONA SNIPER (bot/wick.py, rregullat e 28 shtatorit) me te njejtin kod si boti.

Hyrja ne mbylljen e qiririt M1 te rejection-it (+spread per blerje), SL 2$ pertej zones, TP 20/30/40/60/80/100
pips me 1/6 ne secilin, SL ne hyrje pas TP1. Nje pozicion njeheresh, hyrje 01-20 UTC, e premte mbyllet 19:00 UTC.
    python -m research.zone_sniper <m1.pkl>
"""
import pickle
import sys
from collections import Counter
from datetime import datetime, timezone

from bot import wick
from bot.confluence import weekend_or_offhours
from bot.zones import aggregate


def simulate(m1, e, spread, p):
    buy = e["side"] == "BUY"
    entry = e["entry"] + (spread if buy else 0)
    sl = e["sl"]
    risk = (entry - sl) if buy else (sl - entry)
    if risk <= 0:
        return None
    parts = [1 / len(e["tps"])] * len(e["tps"])
    r_total, idx = 0.0, 0
    stop = sl
    for j in range(e["i"] + 1, min(e["i"] + 4320, len(m1))):
        b = m1[j]
        lo, hi = (b.l, b.h) if buy else (b.l + spread, b.h + spread)
        d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
        if (d.weekday() == 4 and d.hour >= 19) or d.weekday() >= 5:
            x = b.o + (0 if buy else spread)
            r_total += sum(parts[idx:]) * (((x - entry) if buy else (entry - x)) / risk)
            return r_total, j, idx
        if (buy and lo <= stop) or (not buy and hi >= stop):
            r_total += sum(parts[idx:]) * (((stop - entry) if buy else (entry - stop)) / risk)
            return r_total, j, idx
        while idx < len(e["tps"]) and ((buy and hi >= e["tps"][idx]) or (not buy and lo <= e["tps"][idx])):
            tp = e["tps"][idx]
            r_total += parts[idx] * (((tp - entry) if buy else (entry - tp)) / risk)
            idx += 1
            if idx == 1 and p.be_after_tp1:
                stop = entry
        if idx == len(e["tps"]):
            return r_total, j, idx
    x = m1[j].c
    return r_total + sum(parts[idx:]) * (((x - entry) if buy else (entry - x)) / risk), j, idx


def run(m1, p, spread=0.17):
    m15 = aggregate(m1, 15)
    T, free = [], -1
    for e in wick.entries(m1, m15, p):
        if e["i"] <= free or weekend_or_offhours(e["t"], 1, 20, 19):
            continue
        risk = abs(e["entry"] - e["sl"])
        if risk > 25:
            continue
        s = simulate(m1, e, spread, p)
        if s is None:
            continue
        r, j, tps_hit = s
        T.append(dict(e, r=r, tps_hit=tps_hit, risk=risk))
        free = j
    return T


def line(T, name):
    n = len(T)
    s = sum(x["r"] for x in T)
    eq = peak = dd = 0.0
    for x in T:
        eq += x["r"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return (f"{name:26} {n:4} trade {s:+7.1f}R ({s / max(n, 1):+.3f}R/trade) fitime {sum(x['r'] > 0.05 for x in T) / max(n, 1):4.0%}"
            f" DD {dd:5.1f}R")


if __name__ == "__main__":
    m1 = pickle.load(open(sys.argv[1], "rb"))
    p = wick.P()
    for sp in (0.17, 0.30):
        T = run(m1, p, sp)
        print(line(T, f"kosto {sp}$ te gjitha"))
        if sp == 0.17:
            half = m1[len(m1) // 2].t
            print(line([x for x in T if x["t"] < half], "  jan-maj"))
            print(line([x for x in T if x["t"] >= half], "  qer-sht"))
            for tf in wick.PATTERN_TFS:
                print(line([x for x in T if x["tf"] == tf], f"  pattern {tf}"))
            for c in ("A", "B"):
                print(line([x for x in T if x["combo"] == c], f"  kombinimi {c}"))
            print("  TP te arritura:", sorted(Counter(x["tps_hit"] for x in T).items()),
                  "| risku mesatar %.2f$" % (sum(x["risk"] for x in T) / max(len(T), 1)))

# Rezultati (cTrader M1 26 jan - 25 sht 2026, rregullat e 28 shtatorit):
#   kosto 0.17$: 1196 trade +9.3R (+0.008R/trade) fitime 63% DD 28.5R | jan-maj +9.5R, qer-sht -0.2R
#   pattern: H1 14 tr +2.1R | M30 45 tr +4.4R | M15 95 tr -3.6R | M5 227 tr -7.9R | M1 815 tr +14.3R
#   kombinimi A (D1+H4 trend, engulfing H1) 785 tr -22.2R | kombinimi B (D1 trend, engulfing H4) 411 tr +31.5R
#   TP te arritura: 0:410, 1:218, 2:144, 3:140, 4:68, 5:47, 6 (te gjitha):169 | risku mesatar 4.42$
#   kosto 0.30$: 1193 trade -28.1R.
