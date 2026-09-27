"""Kerkim: strategjia "9:27 candle" (opening range breakout i hapjes se NY) ne ar.

Qiri M3 9:27-9:30 (ora e New York-ut) jep high/low. Qiri i pare M3 pas 9:30 qe mbyllet me trup
jashte range-it jep drejtimin; hyrje ne mbyllje (ose ne pullback te niveli i thyer), SL ne anen tjeter
te qiri 9:27 (ose ne mes), TP 1:1 / 1:2 / 1:5. Nje trade ne dite, dalje e detyrueshme ne 16:00 NY.
Ekzekuto: python -m research.orb927 <m1.pkl>
"""
import sys
import pickle
from datetime import datetime, timezone

from bot.news import ny_offset
from bot.zones import aggregate

SPREAD = 0.3
HALF = datetime(2026, 5, 28, tzinfo=timezone.utc).timestamp() * 1000


def run(m1, rr=2.0, sl_mode="range", entry="close", max_wait=20, min_range=0.5, spread=SPREAD):
    m3 = aggregate(m1, 3)
    idx = {b.t: i for i, b in enumerate(m3)}
    days = sorted({datetime.fromtimestamp(b.t / 1000, timezone.utc).date() for b in m3})
    out = []
    for d in days:
        if d.weekday() >= 5:
            continue
        off = ny_offset(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc))
        t927 = int(datetime(d.year, d.month, d.day, 9 + off, 27, tzinfo=timezone.utc).timestamp() * 1000)
        i0 = idx.get(t927)
        if i0 is None:
            continue
        c = m3[i0]
        hi, lo = c.h, c.l
        if hi - lo < min_range:
            continue
        t_end = t927 + (6 * 60 + 33) * 60_000          # 16:00 NY
        sig = None
        for j in range(i0 + 1, min(len(m3), i0 + 1 + max_wait)):
            b = m3[j]
            if min(b.o, b.c) > hi:
                sig = ("BUY", j)
                break
            if max(b.o, b.c) < lo:
                sig = ("SELL", j)
                break
        if not sig:
            continue
        side, j = sig
        buy = side == "BUY"
        e_i = j
        if entry == "close":
            ep = m3[j].c
        else:                                           # pullback te niveli i thyer
            lvl = hi if buy else lo
            e_i = next((k for k in range(j + 1, min(len(m3), j + 21))
                        if (buy and m3[k].l <= lvl) or (not buy and m3[k].h >= lvl)), None)
            if e_i is None:
                continue
            ep = lvl
        entry_px = ep + (spread if buy else 0)
        sl = (lo if sl_mode == "range" else (hi + lo) / 2) if buy else (hi if sl_mode == "range" else (hi + lo) / 2)
        risk = abs(entry_px - sl) + (0 if buy else spread)
        if risk <= 0:
            continue
        tp = entry_px + rr * risk if buy else entry_px - rr * risk
        sl_px = entry_px - risk if buy else entry_px + risk
        r = None
        for k in range(e_i + 1, len(m3)):
            b = m3[k]
            lo_, hi_ = (b.l, b.h) if buy else (b.l + spread, b.h + spread)
            if (buy and lo_ <= sl_px) or (not buy and hi_ >= sl_px):
                r = -1.0
                break
            if (buy and hi_ >= tp) or (not buy and lo_ <= tp):
                r = rr
                break
            if b.t >= t_end:
                r = ((b.c - entry_px) if buy else (entry_px - b.c)) / risk
                break
        if r is not None:
            out.append(dict(t=m3[j].t, r=r, side=side, risk=risk))
    return out


def line(T, name):
    tot = sum(x["r"] for x in T)
    A = sum(x["r"] for x in T if x["t"] < HALF)
    eq = pk = dd = 0
    for x in T:
        eq += x["r"]
        pk = max(pk, eq)
        dd = max(dd, pk - eq)
    w = sum(x["r"] > 0 for x in T)
    return (f"{name:34} {len(T):3} trade {w / max(1, len(T)) * 100:3.0f}% fitime {tot:+6.1f}R DD {dd:5.1f} | "
            f"shk-maj {A:+6.1f} qer-sht {tot - A:+6.1f}")


if __name__ == "__main__":
    m1 = pickle.load(open(sys.argv[1], "rb"))
    for entry in ("close", "pullback"):
        for sl in ("range", "mid"):
            for rr in (1.0, 2.0, 5.0):
                print(line(run(m1, rr, sl, entry), f"hyrje {entry}, SL {sl}, TP 1:{rr:.0f}"))

# Rezultati (ari, M1 nga llogaria, 26 jan - 25 sht 2026, spread 0.3$, 173 dite me thyerje):
#   hyrje ne mbyllje: TP 1:1 -16.2R, 1:2 -20.8R, 1:5 -40.3R (SL ne anen tjeter te qiri 9:27);
#   me SL ne mes te qiri: -1.9R / -3.5R / -18.5R. Hyrje ne pullback: -19R deri -43.5R.
#   Negative ne cdo variant: ne ar thyerja e qiri 9:27 s'ka avantazh. Nuk u fut ne bot.
