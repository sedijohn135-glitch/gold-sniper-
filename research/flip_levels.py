"""Nivele qe ndryshojne rol (rezistence -> support -> rezistence, RBS/SBR) - shembulli 4314.75-4318.41,
15-25 shtator 2026.

Niveli: maje ose fund swing H1 (k=3). Thyerja: mbyllje H1 pertej nivelit >= 0.1 ATR(H1). Retest-i i pare
pas thyerjes (brenda 48 oreve, pasi cmimi largohet >= 0.5 ATR): qiri M5 qe prek nivelin (tol 0.15 ATR)
dhe mbyll ne anen e thyerjes me bisht >= 60% -> hyrje ne mbyllje; SL pertej bishtit + 0.1 ATR (min 3$),
TP 2R / 3R. Njesoj si research/snr.py (A), plus historia e nivelit ne 20 ditet para thyerjes:
  - "rrole": sa swing H1 te llojit TJETER (fund per nje rezistence, maje per nje support) ne te njejtin
    nivel (+-0.15 ATR): niveli ka qene edhe support edhe rezistence (ka ndryshuar rol);
  - "prekje": sa swing H1 gjithsej (cdo lloj) ne ate nivel.
Drawdown: sa larg shkoi cmimi kunder (ne R) para daljes.

    python -m research.flip_levels <hist_m5.pkl> <m5_2026.pkl>
"""
import bisect
import pickle
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

from bot.confluence import weekend_or_offhours
from bot.strategy import atr_series
from bot.zones import aggregate, swings

H1 = 3_600_000
M5 = 300_000
COSTS = (0.17, 0.30)


def setups(m5):
    h1 = aggregate(m5, 60)
    atr = atr_series(h1, 14)
    sw = swings(h1, 3)
    times = [b.t for b in m5]
    swt = [h1[c].t + H1 for c, i, k, v in sw]
    out = []
    for n_sw, (ci, i, kind, lvl) in enumerate(sw):
        buy = kind == "H"
        known = h1[ci].t + H1
        brk = None
        for j in range(ci + 1, min(ci + 240, len(h1))):
            a = atr[j]
            if a != a:
                break
            c = h1[j].c
            if (buy and c > lvl + 0.1 * a) or (not buy and c < lvl - 0.1 * a):
                brk = j
                break
        if brk is None:
            continue
        a = atr[brk]
        # historia e nivelit: swing-et e 20 diteve para thyerjes ne te njejtin nivel
        lo_q = bisect.bisect_left(swt, h1[brk].t - 20 * 86_400_000)
        hi_q = bisect.bisect_right(swt, h1[brk].t)
        other = same = 0
        for q in range(lo_q, hi_q):
            if q == n_sw:
                continue
            _, _, k2, v2 = sw[q]
            if abs(v2 - lvl) <= 0.15 * a:
                if k2 == kind:
                    same += 1
                else:
                    other += 1
        k0 = bisect.bisect_left(times, h1[brk].t + H1)
        away = False
        for k in range(k0, min(k0 + 576, len(m5))):
            b = m5[k]
            if (buy and b.c < lvl - 0.3 * a) or (not buy and b.c > lvl + 0.3 * a):
                break
            if not away:
                away = (b.h >= lvl + 0.5 * a) if buy else (b.l <= lvl - 0.5 * a)
                continue
            rng = b.h - b.l
            if rng <= 0:
                continue
            if buy and b.l <= lvl + 0.15 * a and b.c > lvl and (b.c - b.l) >= 0.6 * rng:
                out.append(dict(i=k, t=b.t + M5, side="BUY", entry_c=b.c, sl=b.l - 0.1 * a, a=a,
                                roles=other, touches=other + same))
                break
            if not buy and b.h >= lvl - 0.15 * a and b.c < lvl and (b.h - b.c) >= 0.6 * rng:
                out.append(dict(i=k, t=b.t + M5, side="SELL", entry_c=b.c, sl=b.h + 0.1 * a, a=a,
                                roles=other, touches=other + same))
                break
    return out


def outcome(m5, c, rr, spread, min_sl):
    """(R, drawdown maksimal ne R para daljes, indeksi i daljes)."""
    buy = c["side"] == "BUY"
    entry = c["entry_c"] + (spread if buy else 0)
    risk = max(abs(entry - c["sl"]), min_sl)
    if risk > 3 * c["a"]:
        return None
    sl = entry - risk if buy else entry + risk
    tp = entry + rr * risk if buy else entry - rr * risk
    mae = 0.0
    for j in range(c["i"] + 1, len(m5)):
        b = m5[j]
        lo, hi = (b.l, b.h) if buy else (b.l + spread, b.h + spread)
        d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
        if (d.weekday() == 4 and d.hour >= 19) or d.weekday() >= 5:
            x = b.o + (0 if buy else spread)
            return ((x - entry) if buy else (entry - x)) / risk, mae, j
        mae = max(mae, ((entry - lo) if buy else (hi - entry)) / risk)
        if (buy and lo <= sl) or (not buy and hi >= sl):
            return -1.0, 1.0, j
        if (buy and hi >= tp) or (not buy and lo <= tp):
            return float(rr), mae, j
    return 0.0, mae, len(m5)


def run(m5, k, t0, t1):
    rows = []
    for c in setups(m5):
        if not (t0 <= c["t"] < t1) or weekend_or_offhours(c["t"], 1, 20, 19):
            continue
        res = {}
        for rr in (2, 3):
            for cost in COSTS:
                o = outcome(m5, c, rr, cost * k, 3 * k)
                if o is None:
                    break
                res[(rr, cost)] = (o[0], o[1], m5[min(o[2], len(m5) - 1)].t)
        if res:
            rows.append((c["t"], c["roles"], c["touches"], res))
    return rows


GROUPS = {
    "te gjitha": lambda roles, touches: True,
    "pa histori (0 prekje)": lambda roles, touches: touches == 0,
    ">= 2 prekje": lambda roles, touches: touches >= 2,
    "ndryshoi rol >= 1": lambda roles, touches: roles >= 1,
    "ndryshoi rol >= 2": lambda roles, touches: roles >= 2,
}


def stats(rows, key, fn):
    n = s = w = 0
    dd = []
    free = 0
    for t, roles, touches, res in sorted(rows, key=lambda x: x[0]):
        if t < free or key not in res or not fn(roles, touches):
            continue
        r, mae, x = res[key]
        n, s, w, free = n + 1, s + r, w + (r > 0.05), x
        if r > 0.05:
            dd.append(mae)
    small = sum(d < 0.25 for d in dd) / max(len(dd), 1)
    return n, s, w, small


if __name__ == "__main__":
    hist = pickle.load(open(sys.argv[1], "rb"))
    per = {}
    for y in range(2016, 2026):
        t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        t1 = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        b5 = [b for b in hist if t0 - 40 * 86_400_000 <= b.t < t1 + 5 * 86_400_000]
        k = statistics.median(b.c for b in b5 if t0 <= b.t < t1) / 4513.71
        per[y] = run(b5, k, t0, t1)
    m26 = pickle.load(open(sys.argv[2], "rb"))
    per[2026] = run(m26, 1.0, m26[0].t + 40 * 86_400_000, 2**62)
    for rr in (2, 3):
        for cost in COSTS:
            print(f"\n=== TP {rr}R | kosto {cost}$ | R per trade, fitime, fitimet me drawdown < 0.25R")
            for g, fn in GROUPS.items():
                line = f"{g:22}"
                for lbl, ys in (("16-20", range(2016, 2021)), ("21-25", range(2021, 2026)), ("2026", (2026,))):
                    N = S = W = 0
                    sm = []
                    for y in ys:
                        n, s, w, small = stats(per[y], (rr, cost), fn)
                        N, S, W = N + n, S + s, W + w
                        sm.append((small, w))
                    small = sum(a * b for a, b in sm) / max(sum(b for a, b in sm), 1)
                    line += f" | {lbl} {N:4} tr {S / max(N, 1):+.3f}R fit {W / max(N, 1):3.0%} dd<0.25R {small:3.0%}"
                print(line, flush=True)

# Rezultati (HistData M5 2016-2025 + cTrader 2026, kosto 0.17$, TP 2R), R per trade | fitimet me drawdown < 0.25R:
#   te gjitha            2016-20 -0.046 (31%) | 2021-25 -0.042 (30%) | 2026 -0.027 (38%)   ~400 trade ne vit
#   pa histori           -0.028 | -0.055 | -0.097
#   >= 2 prekje          -0.058 | -0.020 | -0.033
#   ndryshoi rol >= 1    -0.006 | -0.046 | +0.165 (61 trade)
#   ndryshoi rol >= 2    -0.046 | -0.114 | +0.125 (16 trade)
#   TP 3R: njesoj (-0.23 deri +0.04 historikisht). Nivelet qe kane ndryshuar rol s'japin rezultat me te mire;
#   vetem ~30% e trade-ve fituese kane drawdown < 0.25R (jo "afer zeros").
# Niveli i shembullit (4314.75-4318.41) u kalua shume here pa u shenuar: 17 sht 07:00 thyerje lart, 08:00-09:00
# poshte deri 4306, 10:30 perseri lart; 22 sht retest-e 3-6$ nen nivel; 23 sht 07:30-11:00 ne te dy anet.
