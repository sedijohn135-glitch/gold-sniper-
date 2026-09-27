"""Kerkim: "one candle" (video): qiri qe fshin low-in e qiri te meparshem (sweep) dhe mbyllet mbi
hapjen e qiri te meparshem -> "qiri tjeter zgjerohet 87%" (pasqyra per SELL).

Mat: (1) sa shpesh qiri tjeter kalon high-in e qiri te sinjalit, krahasuar me cdo qiri qe mbyllet lart;
(2) trade: hyrje ne mbyllje (+spread), SL nen low-in e sweep-it, TP 1R/2R, 1 pozicion njeheresh.
Ekzekuto: python -m research.sweep_candle <m5.pkl>
"""
import sys
import pickle
from datetime import datetime, timezone

from bot.zones import aggregate

SPREAD = 0.3
HALF = datetime(2026, 5, 28, tzinfo=timezone.utc).timestamp() * 1000


def signal(p, b):
    if b.l < p.l and b.c > p.o and b.c > b.o:
        return "BUY"
    if b.h > p.h and b.c < p.o and b.c < b.o:
        return "SELL"
    return None


def stats(bars):
    hit = n = base_hit = base_n = 0
    for i in range(1, len(bars) - 1):
        p, b, nx = bars[i - 1], bars[i], bars[i + 1]
        up = b.c > b.o
        base_n += 1
        base_hit += (nx.h > b.h) if up else (nx.l < b.l)
        s = signal(p, b)
        if s:
            n += 1
            hit += (nx.h > b.h) if s == "BUY" else (nx.l < b.l)
    return n, hit / max(1, n), base_hit / max(1, base_n)


def trade(bars, rr):
    out, free = [], -1
    for i in range(1, len(bars) - 1):
        if i <= free:
            continue
        s = signal(bars[i - 1], bars[i])
        if not s:
            continue
        b = bars[i]
        buy = s == "BUY"
        entry = b.c + (SPREAD if buy else 0)
        sl = b.l if buy else b.h + SPREAD
        risk = abs(entry - sl)
        if risk <= 0.3:
            continue
        tp = entry + rr * risk if buy else entry - rr * risk
        for j in range(i + 1, min(len(bars), i + 200)):
            x = bars[j]
            lo, hi = (x.l, x.h) if buy else (x.l + SPREAD, x.h + SPREAD)
            if (buy and lo <= sl) or (not buy and hi >= sl):
                out.append((b.t, -1.0)); free = j; break
            if (buy and hi >= tp) or (not buy and lo <= tp):
                out.append((b.t, rr)); free = j; break
    return out


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    for name, bars in (("M5", m5), ("M15", aggregate(m5, 15)), ("H1", aggregate(m5, 60))):
        n, p, base = stats(bars)
        print(f"{name}: {n} sinjale | qiri tjeter kalon ekstremin {p * 100:.1f}% | cdo qiri {base * 100:.1f}%")
        for rr in (1.0, 2.0):
            T = trade(bars, rr)
            tot = sum(r for _, r in T); A = sum(r for t, r in T if t < HALF)
            print(f"   trade TP {rr:.0f}R: {len(T)} trade, {sum(r > 0 for _, r in T) / max(1, len(T)) * 100:.0f}% fitime, "
                  f"{tot:+.1f}R (shk-maj {A:+.1f}, qer-sht {tot - A:+.1f})")

# Rezultati (ari, 26 jan - 25 sht 2026, spread 0.3$):
#   qiri tjeter kalon ekstremin: M5 75.2% (cdo qiri 68.0%) | M15 75.5% (66.8%) | H1 77.4% (67.2%).
#   Si trade (SL nen sweep, TP 1R/2R): M5 -326R/-217R, M15 -77R/-34R, H1 -6R/-3R. Nuk u fut ne bot.
