"""Kerkim: "snajperi i lajmeve" per arin.

Lajmet e medha te SHBA-se dalin ne ore fikse te New York-ut: 8:30 (CPI, NFP, PPI, shitjet),
10:00 (ISM, JOLTS) dhe 14:00 (FOMC). Pa kalendar historik, lajmi njihet nga vete cmimi:
qiri M5 qe nis ne ate ore me range >= k x ATR(14) dhe trup >= 50% e qirit = reagim lajmi.

Menyrat e tregtimit (pas mbylljes se qirit te lajmit):
  follow   hyrje ne drejtim te kercimit ne mbyllje; SL pertej qirit te lajmit
  confirm  prit 1 qiri: hyrje vetem nese mbyllet pertej ekstremit te qirit te lajmit
  fade     hyrje kundër kercimit (kthim), SL pertej ekstremit
Dalja: TP fiks R, ose trailing (break-even pas 1R, pastaj distance x ADR).
Ekzekuto: python -m research.news <m5.pkl>
"""
import sys
import pickle
from datetime import datetime, timezone, timedelta

from bot.strategy import atr_series, adr_series

SPREAD = 0.3            # spread-i zgjerohet ne lajme
SLIP = 0.3              # rreshqitje ne hyrje
HALF = datetime(2026, 5, 28, tzinfo=timezone.utc).timestamp() * 1000


def ny_offset(d):
    """Sa ore UTC eshte ora e New York-ut (DST: e diela e 2-te e marsit - e diela e 1-re e nentorit)."""
    y = d.year
    mar = datetime(y, 3, 8, tzinfo=timezone.utc)
    start = mar + timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    end = nov + timedelta(days=(6 - nov.weekday()) % 7)
    return 4 if start <= d < end else 5


def news_bars(m5, k=3.0, hours=((8, 30), (10, 0), (14, 0))):
    atr = atr_series(m5, 14)
    out = []
    for i in range(1, len(m5) - 1):
        b = m5[i]
        d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
        if d.weekday() >= 5:
            continue
        off = ny_offset(d)
        if not any(d.hour == (h + off) % 24 and d.minute == mn for h, mn in hours):
            continue
        a = atr[i - 1]
        rng = b.h - b.l
        if a != a or rng < k * a or abs(b.c - b.o) < 0.5 * rng:
            continue
        out.append(i)
    return out


def simulate(m5, idx, adr, mode, exit_mode, rr=2.0, trail_adr=0.4, sl_buf=0.5, max_hold=288):
    trades = []
    free = -1
    for i in idx:
        if i <= free:
            continue
        nb = m5[i]
        up = nb.c > nb.o
        j = i
        if mode == "confirm":
            j = i + 1
            if j >= len(m5):
                continue
            c = m5[j]
            if (up and c.c <= nb.h) or (not up and c.c >= nb.l):
                continue
        buy = up if mode != "fade" else not up
        e_bar = m5[j]
        entry = e_bar.c + (SPREAD + SLIP if buy else -SLIP)
        ext_lo = min(nb.l, e_bar.l)
        ext_hi = max(nb.h, e_bar.h)
        sl = (ext_lo - sl_buf) if buy else (ext_hi + sl_buf + SPREAD)
        risk = abs(entry - sl)
        if risk <= 0 or adr[i] != adr[i] or risk > 0.5 * adr[i]:
            continue
        tp = entry + rr * risk if buy else entry - rr * risk
        best = entry
        x = None
        for q in range(j + 1, min(len(m5), j + max_hold)):
            b = m5[q]
            lo, hi = (b.l, b.h) if buy else (b.l + SPREAD, b.h + SPREAD)
            if (buy and lo <= sl) or (not buy and hi >= sl):
                x = sl
            elif exit_mode == "tp" and ((buy and hi >= tp) or (not buy and lo <= tp)):
                x = tp
            if x is not None:
                break
            if exit_mode == "trail":
                best = max(best, hi) if buy else min(best, lo)
                fav = best - entry if buy else entry - best
                if fav >= risk:
                    sl = max(sl, entry) if buy else min(sl, entry)
                    d = trail_adr * adr[i]
                    sl = max(sl, best - d) if buy else min(sl, best + d)
            d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
            if d.weekday() == 4 and d.hour >= 19:
                x = b.o
                break
        else:
            q = min(len(m5) - 1, j + max_hold - 1)
            x = m5[q].c
        trades.append(dict(t=m5[i].t, r=((x - entry) if buy else (entry - x)) / risk))
        free = q
    return trades


def line(T, name):
    tot = sum(x["r"] for x in T)
    A = sum(x["r"] for x in T if x["t"] < HALF)
    top = sum(sorted((x["r"] for x in T), reverse=True)[:3])
    return (f"{name:38} {len(T):3} trade {sum(x['r'] > 0.05 for x in T):3} fitime {tot:+6.1f}R | "
            f"shk-maj {A:+6.1f} qer-sht {tot - A:+6.1f} | pa top3 {tot - top:+6.1f}")


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    adr = adr_series(m5, 10)
    for k in (2.5, 3.0, 4.0):
        idx = news_bars(m5, k)
        print(f"--- qiri lajmi >= {k} x ATR: {len(idx)} raste")
        for mode in ("follow", "confirm", "fade"):
            for ex, kw in (("tp", dict(rr=2.0)), ("tp", dict(rr=3.0)), ("trail", dict(trail_adr=0.4))):
                name = f"{mode} {ex}" + (f" {kw['rr']:.0f}R" if ex == "tp" else "")
                print(line(simulate(m5, idx, adr, mode, ex, **kw), name))

# Rezultati (ari, M5 nga llogaria, 26 jan - 25 sht 2026; spread 0.3$ + rreshqitje 0.3$):
#   qiri >= 2.5 x ATR (32 raste): follow+trail 25 trade +24.6R (shk-maj +13.1, qer-sht +11.5);
#   follow TP 2R +4.2R; confirm +3.7R (7 trade); fade -12.7R deri -22.0R.
#   >= 3 x ATR: follow+trail +22.2R; >= 4 x ATR: +2.4R. Pa 3 me te mirat: ~-3R.
#   Hyrjet e sniper-it 30-60 min para kercimit: 3-4 trade, -3R deri -4R (arsyeja e ndalimit).
