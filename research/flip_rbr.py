"""Setup-i i pronarit: supply i thyer ne te majte + RBR i fresket ne te djathte ne te njejtin nivel.

BUY (SELL = pasqyra):
  1. Majtas: DBD supply (kembe renie + qiri baze BULLISH + kembe renie qe mbyll nen bazen).
     Zona e shenuar = hija e poshtme e qiririt bullish: [low, open].
  2. Supply-i thyhet paster: qiri bullish me trup >= 60% qe mbyll mbi majen e qiririt baze.
  3. Djathtas, ne te njejtin nivel: RBR i ri (rritje >= 0.8 ATR, baza 1-3 qirinj <= 0.8 ATR, rritje >= 1 ATR
     mbi bazen) me bazen qe mbivendoset me zonen e shenuar (+-0.25 ATR).
  4. Hyrja ne kthimin e pare ne zone pas RBR-se (zona fresh):
       limit: blerje limit ne open-in e qiririt bullish (maja e zones), mbushja ne M1;
       rej:   pas prekjes, mbyllja e pare M1 mbi zone brenda 60 minutave -> blerje me treg.
     SL = low i zones - 0.2 ATR (min 1$), TP 2R / 3R / 4R. Nese SL dhe TP bien ne te njejtin minut: SL.
  5. Konfluencat (te njohura para hyrjes): engulfing bullish i mbyllur H4 / H1 / M30 (nje nga 2 qirinjte
     e fundit), trendline H1 ne rritje (dy swing low) qe arrin ne zone tani, ADR >= 1.6% e cmimit.
Pattern-i kerkohet ne H1, M30, M15, M5 dhe M1. Kosto 0.17$ / 0.30$ ne 4,500$ (shkallezuar me cmimin).

    python -m research.flip_rbr <dosja HistData M1> <m1_2026.pkl>
"""
import bisect
import statistics
import pickle
import sys
from collections import defaultdict
from datetime import datetime, timezone

from bot.confluence import weekend_or_offhours
from bot.strategy import Bar, atr_series
from bot.zones import aggregate, swings
from research.qm_sniper import load_year

M1 = 60_000
REF = 4513.71
TFS = {"H1": 60, "M30": 30, "M15": 15, "M5": 5, "M1": 1}
RRS = (2, 3, 4)
COSTS = (0.17, 0.30)


def mirror(bars):
    return [Bar(b.t, -b.o, -b.l, -b.h, -b.c) for b in bars]


def patterns(B, tf_ms, stat=None):
    """Pattern-et BUY ne qirinjte B: (koha kur njihet RBR, zona lo, zona hi, atr)."""
    a = atr_series(B, 14)
    n = len(B)
    out = []
    st = stat if stat is not None else defaultdict(int)
    for j in range(4, n - 4):
        x = a[j]
        if x != x or x <= 0:
            continue
        base = B[j]
        if not base.c > base.o or base.h - base.l > 1.0 * x:
            continue
        st["baza bullish"] += 1
        # kembe renie hyrese: 1-3 qirinj me renie neto >= 0.8 ATR
        if max(B[j - q].o for q in (1, 2, 3)) - B[j - 1].c < 0.8 * x:
            continue
        st["renie para"] += 1
        # kembe renie dalese: brenda 3 qirinjve mbyllje nen low-in e bazes, renie >= 1 ATR
        if not any(B[q].c < base.l and base.c - B[q].c >= 1.0 * x for q in range(j + 1, j + 4)):
            continue
        st["DBD"] += 1
        zlo, zhi = base.l, base.o
        if zhi - zlo <= 0:
            continue
        st["hija > 0"] += 1
        m = None
        for q in range(j + 2, min(j + 500, n)):
            b = B[q]
            if b.c > base.h:
                rng = b.h - b.l
                if rng > 0 and b.c > b.o and (b.c - b.o) >= 0.5 * rng:
                    m = q
                break
        if m is None:
            continue
        st["thyerje e paster"] += 1
        found = False
        for r in range(m + 1, min(m + 300, n - 4)):
            if B[r].c < zlo:
                break
            ar = a[r]
            if ar != ar:
                continue
            # RBR: rritje 1-3 qirinj >= 0.8 ATR, baza 1-3 qirinj te vegjel, pastaj rritje >= 1 ATR mbi bazen
            if B[r - 1].c - min(B[r - q].o for q in (1, 2, 3)) < 0.8 * ar:
                continue
            for nb in (1, 2, 3):
                bs = B[r:r + nb]
                if any(y.h - y.l > 0.8 * ar for y in bs):
                    break
                blo, bhi = min(y.l for y in bs), max(max(y.o, y.c) for y in bs)
                top = max(y.h for y in bs)
                ob = next((q for q in range(r + nb, min(r + nb + 3, n))
                           if B[q].c > top and B[q].c - bs[-1].c >= 1.0 * ar), None)
                if ob is None:
                    continue
                st["RBR pas thyerjes"] += 1
                if blo <= zhi + 0.25 * x and bhi >= zlo - 0.25 * x:     # i njejti nivel (+-0.25 ATR)
                    st["RBR ne te njejtin nivel"] += 1
                    out.append((B[ob].t + tf_ms, zlo, zhi, x))
                    found = True
                break
            if found:
                break
    return out


def engulf_times(B, tf_ms):
    """Kohet e mbylljes se qirinjve bullish engulfing."""
    return [b.t + tf_ms for p, b in zip(B, B[1:])
            if p.c < p.o and b.c > b.o and b.c > p.o and b.o <= p.c]


def h1_lines(h1):
    """Trendline H1 ne rritje nga dy swing low (k=3): (koha kur njihet, i1, v1, pjerresia, i vdekur)."""
    lows, out = [], []
    for c, i, k, v in swings(h1, 3):
        if k != "L":
            continue
        lows.append((i, v))
        if len(lows) < 2:
            continue
        (i1, v1), (i2, v2) = lows[-2], lows[-1]
        if i2 - i1 < 5 or v2 <= v1:
            continue
        slope = (v2 - v1) / (i2 - i1)
        dead = len(h1)
        for q in range(i2 + 1, min(len(h1), i2 + 240)):
            if h1[q].c < v1 + slope * (q - i1):
                dead = q
                break
        out.append((h1[c].t + 3_600_000, i1, v1, slope, min(dead, i2 + 240)))
    return out


def daily_adr_pct(m1):
    days = {}
    for b in m1:
        d = b.t // 86_400_000
        h, l, c = days.get(d, (b.h, b.l, b.c))
        days[d] = (max(h, b.h), min(l, b.l), b.c)
    ks = sorted(days)
    out = {}
    for i, d in enumerate(ks):
        prev = [days[x] for x in ks[max(0, i - 10):i] if (x + 3) % 7 < 5]
        if len(prev) >= 5:
            out[d] = statistics.mean(abs(h - l) for h, l, c in prev) / abs(days[ks[i - 1]][2]) * 100
    return out


def simulate(m1, e, buy, fill, sl, k, sp, same):
    """R per TP 2R/3R/4R; dalja: (R-te, koha e daljes)."""
    risk = (fill - sl) if buy else (sl - fill)
    if risk <= 0:
        return None
    b = m1[e]
    if same and ((buy and b.l <= sl) or (not buy and b.h + sp >= sl)):
        return {rr: -1.0 for rr in RRS}, b.t + M1
    tps = {rr: fill + rr * risk if buy else fill - rr * risk for rr in RRS}
    res = {}
    j = e
    for j in range(e + 1, min(e + 4320, len(m1))):
        b = m1[j]
        lo, hi = (b.l, b.h) if buy else (b.l + sp, b.h + sp)
        d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
        if (d.weekday() == 4 and d.hour >= 19) or d.weekday() >= 5:
            px = b.o + (0 if buy else sp)
            r = ((px - fill) if buy else (fill - px)) / risk
            for rr in RRS:
                res.setdefault(rr, r)
            break
        if (buy and lo <= sl) or (not buy and hi >= sl):
            for rr in RRS:
                res.setdefault(rr, -1.0)
            break
        for rr, tp in tps.items():
            if rr not in res and ((buy and hi >= tp) or (not buy and lo <= tp)):
                res[rr] = float(rr)
        if len(res) == len(RRS):
            break
    for rr in RRS:
        res.setdefault(rr, 0.0)
    return res, m1[j].t


def candidates(m1, k):
    """Te gjitha hyrjet (te dy anet, te gjitha TF-te, te dyja menyrat) me konfluencat."""
    t1 = [b.t for b in m1]
    adr = daily_adr_pct(m1)
    out = []
    for side, bars in (("BUY", m1), ("SELL", mirror(m1))):
        buy = side == "BUY"
        h1 = aggregate(bars, 60)
        lines = h1_lines(h1)
        h1t = [b.t for b in h1]
        eng = {tf: engulf_times(aggregate(bars, mins), mins * M1) for tf, mins in (("H4", 240), ("H1", 60), ("M30", 30))}
        for tf, mins in TFS.items():
            B = bars if mins == 1 else aggregate(bars, mins)
            for known, zlo, zhi, x in patterns(B, mins * M1):
                # cmimet reale: per SELL pasqyrohen mbrapsht
                lvl = zhi if buy else -zhi                       # kufiri i hyrjes (open i qiririt baze)
                far = zlo if buy else -zlo
                sl = far - max(0.2 * x, 1.0 * k) if buy else far + max(0.2 * x, 1.0 * k)
                s0 = bisect.bisect_left(t1, known)
                for mode in ("limit", "rej"):
                    for cost in COSTS:
                        sp = cost * k
                        e = fill = None
                        same = False
                        for j in range(s0, min(s0 + 300 * mins, len(m1))):
                            b = m1[j]
                            if mode == "limit":
                                if (buy and b.l + sp <= lvl) or (not buy and b.h >= lvl):
                                    e, fill, same = j, (min(lvl, b.o + sp) if buy else max(lvl, b.o)), True
                                    break
                            else:
                                touched = (buy and b.l <= lvl) or (not buy and b.h >= lvl)
                                if touched:
                                    for q in range(j, min(j + 60, len(m1))):
                                        c = m1[q]
                                        if (buy and c.c <= sl) or (not buy and c.c >= sl):
                                            break
                                        if (buy and c.c > lvl) or (not buy and c.c < lvl):
                                            e, fill = q, (c.c + sp if buy else c.c)
                                            break
                                    break
                        if e is None:
                            continue
                        t = m1[e].t + (0 if same else M1)
                        if weekend_or_offhours(t, 1, 20, 19):
                            continue
                        sim = simulate(m1, e, buy, fill, sl, k, sp, same)
                        if sim is None:
                            continue
                        # konfluencat ne kohen e hyrjes
                        f = {}
                        for htf, ms in (("H4", 240), ("H1", 60), ("M30", 30)):
                            et = eng[htf]
                            q = bisect.bisect_right(et, t) - 1
                            f["eng_" + htf] = q >= 0 and t - et[q] <= 2 * ms * M1
                        hi_ = bisect.bisect_right(h1t, t - 3_600_000) - 1
                        ax = x / (1 if mins >= 60 else 1)
                        tl = False
                        for kn, i1, v1, slope, dead in lines:
                            if kn <= t and i1 < hi_ < dead:
                                y = v1 + slope * (hi_ - i1)
                                if zlo - 0.3 * ax <= y <= zhi + 0.3 * ax:
                                    tl = True
                                    break
                        f["tl"] = tl
                        f["adr"] = adr.get(t // 86_400_000, 0) >= 1.6
                        out.append(dict(tf=tf, mode=mode, cost=cost, side=side, t=t, r=sim[0], exit=sim[1], **f))
    return out


FILTERS = {
    "pa filter": lambda c: True,
    "engulfing HTF": lambda c: c["eng_H4"] or c["eng_H1"] or c["eng_M30"],
    "trendline H1": lambda c: c["tl"],
    "engulfing + TL": lambda c: (c["eng_H4"] or c["eng_H1"] or c["eng_M30"]) and c["tl"],
    "ADR>=1.6%": lambda c: c["adr"],
    "engulfing + ADR": lambda c: (c["eng_H4"] or c["eng_H1"] or c["eng_M30"]) and c["adr"],
    "eng + TL + ADR": lambda c: (c["eng_H4"] or c["eng_H1"] or c["eng_M30"]) and c["tl"] and c["adr"],
}


def stats(C, rr):
    n = s = 0
    free = 0
    for c in sorted(C, key=lambda c: c["t"]):
        if c["t"] < free:
            continue
        n, s, free = n + 1, s + c["r"][rr], c["exit"]
    return n, s


if __name__ == "__main__":
    folder, p26 = sys.argv[1], sys.argv[2]
    per = {}
    for y in range(2016, 2026):
        m1 = load_year(folder, y)
        k = statistics.median(b.c for b in m1) / REF
        per[y] = candidates(m1, k)
        print(y, len(per[y]), "hyrje", flush=True)
    per[2026] = candidates(pickle.load(open(p26, "rb")), 1.0)
    print(2026, len(per[2026]), "hyrje", flush=True)
    pickle.dump(per, open("/tmp/flip_rbr.pkl", "wb"))
    for cost in COSTS:
        for mode in ("limit", "rej"):
            for tf in TFS:
                print(f"\n=== {tf} {mode} kosto {cost}$  (R per trade: 2016-20 | 2021-25 | 2026, TP 2R/3R/4R)")
                for fname, fn in FILTERS.items():
                    line = f"{fname:16}"
                    for lbl, ys in (("16-20", range(2016, 2021)), ("21-25", range(2021, 2026)), ("2026", (2026,))):
                        C = [c for y in ys for c in per[y] if c["tf"] == tf and c["mode"] == mode and c["cost"] == cost and fn(c)]
                        parts = []
                        for rr in RRS:
                            n, s = stats(C, rr)
                            parts.append(f"{s / max(n, 1):+.2f}")
                        line += f" | {lbl} {stats(C, 2)[0]:5} tr " + "/".join(parts)
                    print(line, flush=True)

# Rezultati (HistData M1 2016-2025 + cTrader 2026, kosto 0.17$, nje pozicion per TF), R per trade TP 2R/3R/4R:
#   Pattern-i i plote eshte i rralle: H1 ~2-3 ne vit, M30 ~4, M15 ~10, M5 ~50, M1 ~300.
#   M1 limit pa filter: 2016-20 -0.10/-0.08/-0.07 | 2021-25 -0.17/-0.18/-0.15 | 2026 -0.23/-0.18/-0.26
#   M1 rej   pa filter: 2016-20 -0.00/+0.02/+0.03 | 2021-25 -0.13/-0.14/-0.11 | 2026 -0.03/-0.01/-0.19
#   M1 me engulfing HTF: 2016-20 -0.04..-0.15 | 2021-25 -0.12..-0.19 | 2026 +0.20..+0.33 (60 trade)
#   M5 limit/rej: -0.23 deri +0.06 ne te gjitha periudhat.
#   H1+M30+M15 bashke, 10 vjet: limit 190 trade -35R (TP2R); rej 153 trade -8R; me engulfing 58-77 trade
#   ~0; me trendline H1 vetem 12-19 trade ne 10 vjet (s'mjafton per gjykim).
#   Perfundimi: pa avantazh te matshem; konfluencat (engulfing HTF, trendline, ADR) s'e ndryshojne.
