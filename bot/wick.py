"""ZONA SNIPER: rregullat e pronarit (28 shtator 2026), XAUUSD.

Kombinimi (asnjehere kunder trendit):
  - Engulfing i paster (gllaberon te gjithe qiririn e meparshem) ne H4, H1 ose M30, ne drejtim te trendit D1
    (per engulfing H1/M30 edhe trendi H4). Trendi: mbyllja mbi (nen) EMA20 me EMA20 ne rritje (renie).
  - Pattern-i kerkohet ne cdo TF poshte TF-se se engulfing-ut, deri ne M1:
      H4 -> H1, M30, M15, M5, M1 | H1 -> M30, M15, M5, M1 | M30 -> M15, M5, M1
Pattern-i (BUY; SELL = pasqyra): DBD i thyer paster lart; zona = hija e qiririt te fundit bullish te bazes,
  nga open (vija e afert) deri te low (vija e larget).
Konfluenca: trendline me 3 prekje (H4/H1/M30) qe arrin tani ne zone, E DETYRUESHME; SNR ne H4/H1/M30
  (swing ne te majte te bazes) shenohet si konfluence shtese.
Hyrja: pasi cmimi prek zonen, mbyllja e pare M1 jashte saj (rejection).
SL: 20 pips (2$) pertej vijes se larget. TP sipas TF-se se pattern-it (pjese te barabarta, SL ne hyrje pas TP1):
  M1/M5 20/30 pips | M15 30/40/60 | M30 40/60/80 | H1 80/100 pastaj trailing deri 200 pips.
Invalidimi: mbyllje me trup pertej vijes se larget ne TF-ne e pattern-it (vetem wick = ende e vlefshme).

`entries(m1, m15, p)` jep te gjitha hyrjet (backtest); `signal(m1, m15, p)` vetem ate ne qirin e fundit M1.
"""
import bisect
from dataclasses import dataclass

from .strategy import Bar, atr_series
from .zones import SRV, aggregate, swings

MIN = 60_000
TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
PATTERN_TFS = ("H1", "M30", "M15", "M5", "M1")
ENGULF = {"H4": ("H1", "M30", "M15", "M5", "M1"), "H1": ("M30", "M15", "M5", "M1"), "M30": ("M15", "M5", "M1")}
TPS = {"M1": (2.0, 3.0), "M5": (2.0, 3.0), "M15": (3.0, 4.0, 6.0), "M30": (4.0, 6.0, 8.0), "H1": (8.0, 10.0, 20.0)}
TRAIL = {"H1": 5.0}                                    # $: pjesa e fundit ndjek cmimin pas TP2


@dataclass
class P:
    sl_pips: float = 2.0                               # $ pertej vijes se larget (20 pips)
    be_after_tp1: bool = True
    ema: int = 20
    engulf_bars: int = 3                               # engulfing-u ne 3 qirinjte e fundit te TF-se se tij
    max_age_h: float = 72.0                            # zona vlen max 72 ore ose 300 qirinj te TF-se
    need_conf: int = 1                                 # sa nga {TL, SNR} duhen
    require_tl: bool = True                            # trendline-i me 3 prekje eshte i detyrueshem
    tol_atr: float = 0.2                               # toleranca e nivelit (ATR e TF-se se konfluences)
    min_tol: float = 1.0                               # $
    conf_days: float = 10.0                            # SNR: swing-et e 10 diteve para bazes
    tl_touch_atr: float = 0.15                         # prekja e trete e trendline-it: +-0.15 ATR


def _mirror(bars):
    return [Bar(b.t, -b.o, -b.l, -b.h, -b.c) for b in bars]


def _closed(bars, ms, last_close):
    return [b for b in bars if b.t + ms <= last_close]


def _ema(xs, n):
    out, e, a = [], None, 2 / (n + 1)
    for x in xs:
        e = x if e is None else e + a * (x - e)
        out.append(e)
    return out


def _trend_marks(bars, ms, n):
    """(koha e mbylljes, +1/-1/0) per cdo qiri."""
    e = _ema([b.c for b in bars], n)
    out = []
    for i, b in enumerate(bars):
        d = 0
        if i >= max(n, 3):
            if b.c > e[i] and e[i] > e[i - 3]:
                d = 1
            elif b.c < e[i] and e[i] < e[i - 3]:
                d = -1
        out.append((b.t + ms, d))
    return out


def _engulf_marks(bars, ms):
    """Engulfing i paster: gllaberon te gjithe qiririn e meparshem (mbyll pertej high/low-it te tij
    dhe e mbulon me range-in e vet)."""
    out = []
    for p, b in zip(bars, bars[1:]):
        if p.c < p.o and b.c > b.o and b.c > p.h and b.l <= p.l:
            out.append((b.t + ms, 1))
        elif p.c > p.o and b.c < b.o and b.c < p.l and b.h >= p.h:
            out.append((b.t + ms, -1))
    return out


def _at(marks, keys, t):
    i = bisect.bisect_right(keys, t) - 1
    return marks[i][1] if i >= 0 else 0


def _lines3(bars, ms, touch_atr):
    """Trendline me 3 prekje: nga swing low ne rritje (+1) dhe swing high ne renie (-1), e pathyer me mbyllje.
    (njihet, drejtimi, i1, v1, pjerresia, i vdekur)."""
    atr = atr_series(bars, 14)
    sw = swings(bars, 3)
    out = []
    for kind, d in (("L", 1), ("H", -1)):
        pts = [(c, i, v) for c, i, k, v in sw if k == kind]
        for a in range(len(pts)):
            for b in range(a + 1, min(a + 8, len(pts))):
                c1, i1, v1 = pts[a]
                c2, i2, v2 = pts[b]
                if i2 - i1 < 3 or (d == 1 and v2 <= v1) or (d == -1 and v2 >= v1):
                    continue
                slope = (v2 - v1) / (i2 - i1)
                third = None
                for q in range(b + 1, min(b + 8, len(pts))):
                    c3, i3, v3 = pts[q]
                    x = atr[i3]
                    if x == x and abs(v3 - (v1 + slope * (i3 - i1))) <= touch_atr * x:
                        third = (c3, i3)
                        break
                if third is None:
                    continue
                dead = min(len(bars), third[1] + 240)
                for q in range(i1 + 1, dead):
                    y = v1 + slope * (q - i1)
                    x = atr[q] if atr[q] == atr[q] else 0.0
                    if (d == 1 and bars[q].c < y - 0.1 * x) or (d == -1 and bars[q].c > y + 0.1 * x):
                        dead = q
                        break
                if dead > third[1]:
                    out.append((bars[third[0]].t + ms, d, i1, v1, slope, dead))
    return out


def _patterns(B, ms):
    """Zonat BUY ne qirinjte B: (low, open, koha e thyerjes, atr, koha e bazes)."""
    atr = atr_series(B, 14)
    n = len(B)
    out = []
    for j in range(9, n - 2):
        x = atr[j]
        if x != x or x <= 0:
            continue
        base = B[j]
        if not base.c > base.o or base.h - base.l > 1.5 * x or base.o - base.l <= 0:
            continue
        if max(B[q].h for q in range(j - 8, j)) - base.l < 1.5 * x:
            continue
        lo_i = next((q for q in range(j + 1, min(j + 5, n)) if B[q].c < base.l and base.c - B[q].c >= 1.0 * x), None)
        if lo_i is None:
            continue
        for q in range(lo_i + 1, min(lo_i + 200, n)):
            b = B[q]
            if b.c > base.h:
                rng = b.h - b.l
                if rng > 0 and b.c > b.o and (b.c - b.o) >= 0.5 * rng:
                    out.append((base.l, base.o, b.t + ms, x, base.t))
                break
    return out


def entries(m1, m15, p: P):
    """Te gjitha hyrjet: dict(t, i, side, entry, sl, tps, tp_offsets, trail, tf, combo (TF e engulfing-ut),
    near, far, tl, snr)."""
    if not m1 or not m15:
        return []
    last = m1[-1].t + MIN
    T = {"M1": m1, "M5": _closed(aggregate(m1, 5), 5 * MIN, last), "M15": _closed(m15, 15 * MIN, last)}
    T["M30"] = _closed(aggregate(T["M15"], 30), 30 * MIN, last)
    T["H1"] = _closed(aggregate(T["M15"], 60), 60 * MIN, last)
    T["H4"] = _closed(aggregate(T["M15"], 240, SRV), 240 * MIN, last)
    T["D1"] = _closed(aggregate(T["M15"], 1440, SRV), 1440 * MIN, last)
    ms = {tf: TF_MIN[tf] * MIN for tf in T}
    trend = {tf: _trend_marks(T[tf], ms[tf], p.ema) for tf in ("D1", "H4")}
    trend_k = {tf: [x[0] for x in v] for tf, v in trend.items()}
    eng = {tf: _engulf_marks(T[tf], ms[tf]) for tf in ENGULF}
    eng_k = {tf: [x[0] for x in v] for tf, v in eng.items()}
    ctx = {}
    for tf in ("H4", "H1", "M30"):
        B = T[tf]
        sw = sorted((B[c].t + ms[tf], v) for c, i, k, v in swings(B, 3))
        ctx[tf] = dict(t=[b.t for b in B], atr=atr_series(B, 14), lines=_lines3(B, ms[tf], p.tl_touch_atr),
                       sw=sw, swk=[x[0] for x in sw])
    t1 = [b.t for b in m1]

    def allowed(t, d, tf):
        """TF-ja e engulfing-ut qe e lejon kete hyrje (me e larta), ose None."""
        if _at(trend["D1"], trend_k["D1"], t) != d:
            return None
        for etf, below in ENGULF.items():
            if tf not in below or (etf != "H4" and _at(trend["H4"], trend_k["H4"], t) != d):
                continue
            k = eng_k[etf]
            for q in range(bisect.bisect_left(k, t - p.engulf_bars * ms[etf]), bisect.bisect_right(k, t)):
                if eng[etf][q][1] == d:
                    return etf
        return None

    def confluence(t, zlo, zhi, d, tbase):
        tl = snr = False
        for tf, cx in ctx.items():
            ci = bisect.bisect_right(cx["t"], t - ms[tf]) - 1
            if ci < 14:
                continue
            a = cx["atr"][ci]
            tol = max(p.tol_atr * a if a == a else 0.0, p.min_tol)
            lo, hi = zlo - tol, zhi + tol
            if not tl:
                for kn, ld, i1, v1, slope, dead in cx["lines"]:
                    if ld == d and kn <= t and i1 < ci < dead and lo <= v1 + slope * (ci - i1) <= hi:
                        tl = True
                        break
            if not snr:
                swk = cx["swk"]
                for q in range(bisect.bisect_left(swk, tbase - p.conf_days * 86_400_000), bisect.bisect_left(swk, tbase)):
                    if lo <= cx["sw"][q][1] <= hi:
                        snr = True
                        break
        return tl, snr

    out = []
    for tf in PATTERN_TFS:
        B = T[tf]
        tb = [b.t for b in B]
        age = min(p.max_age_h * 3_600_000, 300 * ms[tf])
        for d, bars in ((1, B), (-1, _mirror(B))):
            for zlo, zhi, known, x, tbase in _patterns(bars, ms[tf]):
                # vijat reale: near = vija ku hyhet, far = vija e SL-se
                near, far = (zhi, zlo) if d == 1 else (-zhi, -zlo)
                # invalidimi: mbyllja e pare e TF-se pertej vijes se larget
                inval = known + age
                for q in range(bisect.bisect_left(tb, known), len(B)):
                    if B[q].t + ms[tf] > inval:
                        break
                    if (d == 1 and B[q].c < far) or (d == -1 and B[q].c > far):
                        inval = B[q].t + ms[tf]
                        break
                touched = False
                for j in range(bisect.bisect_left(t1, known), len(m1)):
                    b = m1[j]
                    t = b.t + MIN
                    if t > inval:
                        break
                    if not touched:
                        touched = (b.l <= near) if d == 1 else (b.h >= near)
                        if not touched:
                            continue
                    if (d == 1 and b.c > near) or (d == -1 and b.c < near):
                        combo = allowed(t, d, tf)
                        tl, snr = confluence(t, min(near, far), max(near, far), d, tbase) if combo else (False, False)
                        if not combo or tl + snr < p.need_conf or (p.require_tl and not tl):
                            touched = False              # rejection pa kushtet: pritet prekja tjeter
                            continue
                        sl = far - p.sl_pips if d == 1 else far + p.sl_pips
                        tps = [b.c + d * x_ for x_ in TPS[tf]]
                        out.append(dict(t=t, i=j, side="BUY" if d == 1 else "SELL", entry=b.c, sl=sl, tps=tps,
                                        tp_offsets=TPS[tf], trail=TRAIL.get(tf, 0.0),
                                        tf=tf, combo=combo, near=near, far=far, tl=tl, snr=snr))
                        break
    out.sort(key=lambda e: e["t"])
    return out


def signal(m1, m15, p: P):
    """Hyrja ne mbylljen e qiririt te fundit M1, ose None."""
    last = m1[-1].t + MIN if m1 else 0
    for e in entries(m1, m15, p):
        if e["t"] == last:
            return e
    return None


def split_volume(volume, step, parts=6):
    """Ndan volumin ne `parts` pjese te barabarta (shumefisha te `step`)."""
    units = int(volume // step)
    n = max(1, min(parts, units))
    base, extra = divmod(units, n)
    return [(base + (1 if i < extra else 0)) * step for i in range(n)]
