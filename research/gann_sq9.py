"""Kerkim: formula Gann "Square of Nine" me 0.618 (video): nga nje fund -> rezistenca (sqrt(P)+x)^2,
nga nje maje -> mbeshtetja (sqrt(P)-x)^2. A reagon ari me shpesh te x = 0.618 se te x te tjera?

Majat/fundet: swing-et H4 (te konfirmuara). Niveli vlen 10 dite pas konfirmimit. Te prekja e pare (M5):
"reagim" = cmimi kthehet >= 0.25 x ADR nga niveli para se ta kaloje >= 0.25 x ADR.
Ekzekuto: python -m research.gann_sq9 <m5.pkl>
"""
import bisect
import sys
import pickle
from math import sqrt

from bot.strategy import adr_series
from bot.zones import SRV, aggregate, swings

OFFSETS = (0.25, 0.4, 0.5, 0.55, 0.6, 0.618, 0.65, 0.7, 0.75, 0.9, 1.0)


def levels(m5, x, k=2, days=10):
    h4 = aggregate(m5, 240, SRV)
    out = []
    for c, i, kind, v in swings(h4, k):
        lvl = (sqrt(v) - x) ** 2 if kind == "H" else (sqrt(v) + x) ** 2
        t0 = h4[c].t + 4 * 3_600_000
        out.append(("S" if kind == "L" else "D", lvl, t0, t0 + days * 86_400_000))
    return out


def reactions(m5, adr, lv, move=0.25):
    times = [b.t for b in m5]
    res = []
    for kind, lvl, t0, t1 in lv:
        i = bisect.bisect_left(times, t0)
        # prekja e pare: cmimi vjen nga ana e duhur dhe e prek nivelin
        while i < len(m5) and m5[i].t < t1:
            b = m5[i]
            if (kind == "S" and b.h >= lvl) or (kind == "D" and b.l <= lvl):
                break
            i += 1
        if i >= len(m5) or m5[i].t >= t1 or adr[i] != adr[i]:
            continue
        d = move * adr[i]
        ok = None
        for b in m5[i:i + 288]:
            if kind == "S":
                if b.h >= lvl + d:
                    ok = False
                    break
                if b.l <= lvl - d:
                    ok = True
                    break
            else:
                if b.l <= lvl - d:
                    ok = False
                    break
                if b.h >= lvl + d:
                    ok = True
                    break
        if ok is not None:
            res.append(ok)
    return res


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    adr = adr_series(m5, 10)
    for x in OFFSETS:
        r = reactions(m5, adr, levels(m5, x))
        print(f"x = {x:5.3f}: {len(r):3} prekje | reagim {sum(r) / max(1, len(r)) * 100:5.1f}%")

# Rezultati (ari, M5 nga llogaria, 26 jan - 25 sht 2026), reagim >= 0.25 x ADR para thyerjes 0.25 x ADR:
#   x=0.25 21.9% | 0.4 33.5% | 0.5 37.6% | 0.55 40.6% | 0.6 40.2% | 0.618 42.0% | 0.65 44.1% |
#   0.7 46.8% | 0.75 46.4% | 0.9 49.7% | 1.0 41.6%  (170-265 prekje per x)
#   Reagimi rritet ngadale me distancen (sa me larg maja/fundi, aq me e zgjatur levizja) pa asnje kulm
#   te 0.618; te gjitha nen 50%: ne keto nivele cmimi me shpesh vazhdon se kthehet. Nuk u fut ne bot.
