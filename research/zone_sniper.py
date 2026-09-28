"""Backtest i modulit live ZONA SNIPER (bot/wick.py) me te njejtin kod si boti.

Hyrja ne mbylljen e qiririt M5 te rejection-it (+spread per blerje), SL/TP fikse, nje pozicion njeheresh,
hyrje 01-20 UTC, e premte mbyllet 19:00 UTC.
    python -m research.zone_sniper <m5.pkl> [k]
"""
import pickle
import sys
from datetime import datetime, timezone

from bot import wick
from bot.confluence import weekend_or_offhours
from research.hierarchy import outcome


def run(m5, p, spread=0.2, k=1.0, t0=0, t1=2**62):
    T, free = [], -1
    for e in wick.entries(m5, p):
        t = m5[e["i"]].t + wick.M5
        if e["i"] <= free or not (t0 <= t < t1) or weekend_or_offhours(t, 1, 20, 19):
            continue
        buy = e["side"] == "BUY"
        risk = abs(e["entry"] + (spread if buy else 0) - e["sl"])
        if risk < 3 * k or risk > 25 * k:
            continue
        c = dict(i=e["i"], side=e["side"], entry_c=e["entry"], sl=e["sl"])
        r, j = outcome(m5, c, e["tp"], min_sl=3 * k, spread=spread)
        T.append(dict(t=t, r=r, kind=e["kind"], side=e["side"], entry=e["entry"], sl=e["sl"], tp=e["tp"]))
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
    return f"{name:28} {n:4} trade {s:+7.1f}R ({s / max(n, 1):+.3f}R/trade) fitime {sum(x['r'] > 0.05 for x in T) / max(n, 1):4.0%} DD {dd:5.1f}R"


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    k = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    p = wick.scaled(wick.P(), k)
    for sp in (0.17, 0.30):
        T = run(m5, p, sp * k, k)
        print(line(T, f"kosto {sp}$ te gjitha"))
        print(line([x for x in T if x["kind"] == "zone"], "  zona (me engulfing)"))
        print(line([x for x in T if x["kind"] == "flip"], "  kunder (zona deshtoi)"))

# Rezultati (cTrader M5 26 jan - 25 sht 2026, kosto 0.17$), P e botit (SL 0.5 ATR, TP 2R min 10$):
#   531 trade +37.3R (+0.070R/trade) fitime 36% DD 25.6R | janar-maj -6.1R, qershor-shtator +43.4R | kunder +3.1R
# Variante (te gjitha: gjysma e pare negative, e dyta pozitive):
#   SL 0.2 ATR TP 2R +11.9R | SL 0.2 ATR TP 3R +25.4R | SL 1 ATR TP 1.5R +40.4R | SL 1 ATR TP 3R +38.0R
# Shembujt e pronarit: 23 sht 12:25 SELL (kunder) +2R, 25 sht 11:10 SELL (kunder) +2R; 22 sht 09:10 BUY
# (SL 0.5 ATR) mbijeton dip-in 4312.12 te 09:30.
