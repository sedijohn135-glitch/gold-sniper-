"""Backtest i modulit te hierarkise (bot/hierarchy.py) mbi qirinj M5.

Perdor te njejtin kod sinjali si boti live. Ekzekuto nga rrenja e repo-s:
python -m research.hierarchy <m5.pkl>
"""
import sys
import pickle
from datetime import datetime, timezone

from bot.confluence import weekend_or_offhours
from bot.hierarchy import FEATS, P, prepare, candidates, pick  # noqa: F401

SPREAD = 0.2


def outcome(m5, c, tp, close_friday_utc=19, min_sl=1.0, slip=0.0, spread=None, closed=None):
    """Dalja e nje kandidati: (R, indeksi i daljes). `slip` = rreshqitja e hyrjes ne $.
    `closed(t_ms)`: kur tregu i simbolit mbyllet (pozicioni del ne hapje); None = e premte 19:00 UTC."""
    SPREAD = globals()["SPREAD"] if spread is None else spread
    buy = c["side"] == "BUY"
    entry = c["entry_c"] + (SPREAD if buy else 0) + (slip if buy else -slip)
    risk = max(abs(entry - c["sl"]), min_sl)
    sl = entry - risk if buy else entry + risk
    for j in range(c["i"] + 1, len(m5)):
        b = m5[j]
        lo, hi = (b.l, b.h) if buy else (b.l + SPREAD, b.h + SPREAD)
        x = sl if ((buy and lo <= sl) or (not buy and hi >= sl)) else \
            tp if ((buy and hi >= tp) or (not buy and lo <= tp)) else None
        if x is None and closed is not None:
            if closed(b.t):
                x = b.o + (0 if buy else SPREAD)
        elif x is None and close_friday_utc >= 0:
            d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
            if (d.weekday() == 4 and d.hour >= close_friday_utc) or d.weekday() >= 5:
                x = b.o
        if x is not None:
            return ((x - entry) if buy else (entry - x)) / risk, j
    return 0.0, len(m5)


def simulate(m5, cands, need, min_k, min_rr, start_h=1, end_h=20, cache=None, min_sl=1.0, slip=0.0, max_rr=0.0):
    """need: tipet e detyrueshme; min_k: sa konfirmime minimum. Nje pozicion njeheresh."""
    cache = {} if cache is None else cache
    trades, free = [], -1
    for c in cands:
        if c["i"] <= free or len(c["feats"]) < min_k or not need <= c["feats"]:
            continue
        if weekend_or_offhours(c["t"], start_h, end_h, 19):
            continue
        risk = max(c["risk"], min_sl)
        tp = next((x for x in c["tps"] if abs(x - c["entry_c"]) >= min_rr * risk), None)
        if tp is None:
            continue
        if max_rr > 0 and abs(tp - c["entry_c"]) > max_rr * risk:
            tp = c["entry_c"] + (max_rr * risk if c["side"] == "BUY" else -max_rr * risk)
        key = (c["i"], c["side"], tp, min_sl, slip)
        if key not in cache:
            cache[key] = outcome(m5, c, tp, min_sl=min_sl, slip=slip)
        r, j = cache[key]
        trades.append(dict(t=c["t"], r=r, side=c["side"], feats=c["feats"], htf=c["htf"]))
        free = j
    return trades


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    p = P()
    C = candidates(m5, p, prepare(m5, p))
    T = simulate(m5, C, frozenset(p.need), 0, p.min_rr, min_sl=p.min_sl)
    print(len(C), "kandidate |", len(T), "trade", f"{sum(x['r'] for x in T):+.1f}R")

# Rezultati (M5 nga llogaria, 26 jan - 25 sht 2026), muri H1, dritare 8 ore, TP >= 2R, SL >= 3$:
#   bos + ao: 214 trade, 27% fitime, +100.2R, DD 14.8R (shk-maj +36.9R, qer-sht +63.3R).
#   Vetem ao: 348 trade +94.8R por DD 34.6R. Muri H4 me bos + ao: 87 trade, -9.5R.
#   Mesatarja per kandidat (TP >= 3R): flip +0.19R, ao +0.10R, bos -0.03R, ltf -0.15R,
#   qm -0.38R, tl -0.55R. Fqinjet (dritare 7-10 ore, wick 0.4-0.6, SL buf 0.3-1.0, TP 1.5-3R)
#   dalin te gjitha +43R deri +120R. Stres: rreshqitje 0.3$ + TP max 10R: +57.6R.
#   10 trade-t me te mira japin ~100R: pa to rezultati eshte afer zeros.
#   Krahas sniper + konfluence (pozicione te vecanta): 749 trade, +273.8R, DD 16.9R, 8/8 muaj.
