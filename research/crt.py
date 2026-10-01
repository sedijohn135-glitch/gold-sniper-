"""Candle Range Theory (ICT, te Yanu Emma / Stranger): range-i i dites se djeshme (C1). Sot cmimi kalon njerin skaj
(sweep) dhe nje qiri H4 MBYLLET perseri brenda range-it -> hyrje ne hapjen e qirit tjeter H4 drejt skajit tjeter.
SL pertej majes/fundit te sweep-it + 0.5$, TP = skaji tjeter i range-it (ose `rr` R nese > `max_rr`), BE 1R,
rregullat e botit (02:00-22:00, 22:30, 1 pozicion, stop pas 2 humbjeve). Ekzekutimi ne M5.

    python -m research.crt <ct_XAUUSD_m5.pkl> [variantet]
"""
import pickle
import statistics
import sys
from datetime import datetime, timezone

from bot.zones import aggregate
from research.qt_smt import lt, stats

D1, H4 = 86_400_000, 4 * 3_600_000


def run(m5, k=1.0, spread=0.2, p=None):
    p = dict(dict(tp="range", rr=3.0, max_rr=6.0, min_rr=1.0, buf=0.5, min_sl=3.0, max_sl=25.0, start=2, maxloss=2, be=1.0), **(p or {}))
    d1 = aggregate(m5, 1440, offset_ms=2 * 3_600_000)
    h4 = aggregate(m5, 240)
    prev = {}
    for a, b in zip(d1, d1[1:]):
        prev[b.t] = a
    sig = {}                     # koha e hyrjes -> dict
    day_of = lambda t: ((t + 2 * 3_600_000) // D1) * D1 - 2 * 3_600_000
    hi_sweep, lo_sweep, cur = {}, {}, None
    for b in h4:
        d = day_of(b.t)
        c1 = prev.get(d)
        if c1 is None:
            continue
        if d != cur:
            cur, sh, sl_ = d, None, None
        if b.h > c1.h:
            sh = max(sh or b.h, b.h)
        if b.l < c1.l:
            sl_ = min(sl_ or b.l, b.l)
        if sh is not None and c1.l < b.c < c1.h and b.h >= sh:
            sig[b.t + H4] = dict(side="SELL", ext=sh, tgt=c1.l)
        elif sl_ is not None and c1.l < b.c < c1.h and b.l <= sl_:
            sig[b.t + H4] = dict(side="BUY", ext=sl_, tgt=c1.h)
    T, pos, per_day, loss_day = [], None, {}, {}
    for g in m5:
        L = lt(g.t)
        if pos:
            sell = pos["side"] == "SELL"
            o, hi, lo = (g.o + spread, g.h + spread, g.l + spread) if sell else (g.o, g.h, g.l)
            x = None
            if L.weekday() >= 5 or (L.hour, L.minute) >= (22, 30):
                x = g.o + (spread if sell else 0)
            elif (sell and o >= pos["sl"]) or (not sell and o <= pos["sl"]):
                x = o
            elif (sell and hi >= pos["sl"]) or (not sell and lo <= pos["sl"]):
                x = pos["sl"]
            elif (sell and lo <= pos["tp"]) or (not sell and hi >= pos["tp"]):
                x = pos["tp"]
            else:
                fav = (pos["entry"] - lo) if sell else (hi - pos["entry"])
                if p["be"] and fav >= p["be"] * pos["risk"]:
                    pos["sl"] = min(pos["sl"], pos["entry"] - spread) if sell else max(pos["sl"], pos["entry"] + spread)
            if x is not None:
                pnl = (pos["entry"] - x) if sell else (x - pos["entry"])
                pos.update(usd=pnl / k, r=pnl / pos["risk"])
                T.append(pos)
                if pnl < 0:
                    dd = lt(pos["t"]).date(); loss_day[dd] = loss_day.get(dd, 0) + 1
                pos = None
        s = sig.get(g.t)
        if s and pos is None and L.weekday() < 5 and p["start"] <= L.hour < 22 and per_day.get(L.date(), 0) < 4 \
                and not (p["maxloss"] and loss_day.get(L.date(), 0) >= p["maxloss"]):
            sell = s["side"] == "SELL"
            entry = g.o + (0 if sell else spread)
            slp = s["ext"] + p["buf"] * k if sell else s["ext"] - p["buf"] * k
            risk = max(abs(slp - entry), p["min_sl"] * k)
            reward = (entry - s["tgt"]) if sell else (s["tgt"] - entry)
            if risk <= p["max_sl"] * k and reward >= p["min_rr"] * risk and ((sell and slp > entry) or (not sell and slp < entry)):
                tp = s["tgt"] if (p["tp"] == "range" and reward <= p["max_rr"] * risk) else \
                    (entry - p["rr"] * risk if sell else entry + p["rr"] * risk)
                pos = dict(side=s["side"], entry=entry, risk=risk, t=g.t, sl=entry + risk if sell else entry - risk, tp=tp)
                per_day[L.date()] = per_day.get(L.date(), 0) + 1
    return T


if __name__ == "__main__":
    G = pickle.load(open(sys.argv[1], "rb"))
    V = eval(sys.argv[2]) if len(sys.argv) > 2 else {"CRT": {}}
    for name, kw in V.items():
        R = {}
        for y in range(2016, 2027):
            t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            t1 = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            g = [b for b in G if t0 - 5 * D1 <= b.t < t1]
            k = 1.0 if y == 2026 else statistics.median(b.c for b in g) / 4513.71
            R[y] = [x for x in run(g, k, 0.2 * k, kw) if t0 <= x["t"] < t1]
        H = [x for y, v in R.items() if y < 2026 for x in v]
        print(f"{name:24} | 2026 {stats(R[2026])} | 10v {stats(H)} | " +
              " ".join(f"{y % 100}:{sum(x['usd'] for x in v):+.0f}" for y, v in sorted(R.items())), flush=True)
