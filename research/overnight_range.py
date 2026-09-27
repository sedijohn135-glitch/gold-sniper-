"""Kerkim: "overnight range" (video): range 18:00 -> 9:30 New York; qiri i pare M15 pas 9:30 mbyllet
mbi range -> BUY, nen range -> SELL (ndryshe s'ka trade). Varianti "first": qiri i pare M15 i dites
(deri 12:00 NY) qe mbyllet jashte range-it. SL: ana tjeter e qiri (candle) ose mesi i range-it (mid);
TP 1R / 2R ose mbajtje deri 16:00 NY. Ekzekuto: python -m research.overnight_range <m5.pkl>
"""
import sys
import pickle
from datetime import datetime, timezone, timedelta

from bot.news import ny_offset
from bot.zones import aggregate

SPREAD = 0.3
HALF = datetime(2026, 5, 28, tzinfo=timezone.utc).timestamp() * 1000


def run(m15, mode="open", sl_mode="candle", rr=2.0):
    idx = {b.t: i for i, b in enumerate(m15)}
    days = sorted({datetime.fromtimestamp(b.t / 1000, timezone.utc).date() for b in m15})
    out = []
    for d in days:
        if d.weekday() >= 5:
            continue
        off = ny_offset(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc))
        t930 = int((datetime(d.year, d.month, d.day, 9, 30, tzinfo=timezone.utc) + timedelta(hours=off)).timestamp() * 1000)
        t_start = t930 - int(15.5 * 3_600_000)             # 18:00 NY e dites se meparshme
        i0 = idx.get(t930)
        if i0 is None:
            continue
        rng = [b for b in m15[max(0, i0 - 70):i0] if b.t >= t_start]
        if len(rng) < 20:
            continue
        hi, lo = max(b.h for b in rng), min(b.l for b in rng)
        last = i0 + 1 if mode == "open" else i0 + 10      # deri 12:00 NY
        sig = None
        for j in range(i0, min(last, len(m15))):
            b = m15[j]
            if b.c > hi:
                sig = ("BUY", j); break
            if b.c < lo:
                sig = ("SELL", j); break
        if not sig:
            continue
        side, j = sig
        buy = side == "BUY"
        b = m15[j]
        entry = b.c + (SPREAD if buy else 0)
        sl = (b.l if buy else b.h + SPREAD) if sl_mode == "candle" else (hi + lo) / 2
        risk = abs(entry - sl)
        if risk <= 0.3:
            continue
        tp = (entry + rr * risk if buy else entry - rr * risk) if rr else None
        t_end = t930 + int(6.5 * 3_600_000)
        r = None
        for k in range(j + 1, len(m15)):
            x = m15[k]
            lo_, hi_ = (x.l, x.h) if buy else (x.l + SPREAD, x.h + SPREAD)
            if (buy and lo_ <= sl) or (not buy and hi_ >= sl):
                r = -1.0; break
            if tp and ((buy and hi_ >= tp) or (not buy and lo_ <= tp)):
                r = rr; break
            if x.t >= t_end:
                r = ((x.c - entry) if buy else (entry - x.c)) / risk; break
        if r is not None:
            out.append((b.t, r))
    return out


if __name__ == "__main__":
    m15 = aggregate(pickle.load(open(sys.argv[1], "rb")), 15)
    for mode in ("open", "first"):
        for sl in ("candle", "mid"):
            for rr in (1.0, 2.0, 0):
                T = run(m15, mode, sl, rr)
                tot = sum(r for _, r in T); A = sum(r for t, r in T if t < HALF)
                print(f"{'qiri 9:30' if mode == 'open' else 'i pari jashte (deri 12:00)':26} SL {sl:6} "
                      f"TP {('%.0fR' % rr) if rr else 'deri 16:00':10}: {len(T):3} trade, "
                      f"{sum(r > 0 for _, r in T) / max(1, len(T)) * 100:3.0f}% fitime, {tot:+6.1f}R "
                      f"(shk-maj {A:+.1f}, qer-sht {tot - A:+.1f})")

# Rezultati (ari, 26 jan - 25 sht 2026): qiri 9:30 mbyllet jashte range-it vetem 20 here ne 8 muaj,
#   -4R deri -9R; "i pari jashte deri 12:00": 83 trade, -5.8R deri -24.3R. Negative ne cdo variant.
