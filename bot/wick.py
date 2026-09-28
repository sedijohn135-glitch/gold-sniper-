"""ZONA SNIPER: rregullat e pronarit (28 shtator 2026), XAUUSD.

Trendi (asnjehere kunder tij):
  A: D1 dhe H4 ne trend + engulfing H1 ne te njejtin drejtim (6 oret e fundit) -> pattern ne M30, M15, M5, M1
  B: D1 ne trend + engulfing H4 ne te njejtin drejtim (12 oret e fundit)       -> pattern ne H1, M30, M15, M5, M1
  Trendi i nje TF: mbyllja mbi (nen) EMA20 dhe EMA20 me e larte (me e ulet) se 3 qirinj me pare.
Pattern-i (BUY; SELL = pasqyra):
  DBD: cmimi bie ne baze, qiri i fundit bullish i bazes, renie nen te; thyerje paster lart (mbyllje mbi majen
  e qiririt, trup >= 50%). Zona = hija e qiririt nga open (vija e afert) deri te low (vija e larget).
Konfluenca: trendline (H1/M30/M15) ose SNR (swing H4/H1/M30/M15 ne te majte) ne nivelin e zones.
Hyrja: pasi cmimi prek zonen, mbyllja e pare M1 jashte saj (rejection).
SL: 20 pips (2$) pertej vijes se larget. TP: 20/30/40/60/80/100 pips, 1/6 ne secilin; SL ne hyrje pas TP1.
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
COMBO_A = ("M30", "M15", "M5", "M1")
COMBO_B = ("H1", "M30", "M15", "M5", "M1")


@dataclass
class P:
    sl_pips: float = 2.0                               # $ pertej vijes se larget (20 pips)
    tps: tuple = (2.0, 3.0, 4.0, 6.0, 8.0, 10.0)       # $ nga hyrja (20-100 pips)
    be_after_tp1: bool = True
    ema: int = 20
    h1_engulf_h: float = 6.0
    h4_engulf_h: float = 12.0
    max_age_h: float = 72.0                            # zona vlen max 72 ore ose 300 qirinj te TF-se
    need_conf: int = 1                                 # sa nga {TL, SNR} duhen
    tol_atr: float = 0.2                               # toleranca e nivelit (ATR e TF-se se konfluences)
    min_tol: float = 1.0                               # $
    conf_days: float = 10.0                            # SNR: swing-et e 10 diteve para bazes


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
    out = []
    for p, b in zip(bars, bars[1:]):
        if p.c < p.o and b.c > b.o and b.c > p.o and b.o <= p.c:
            out.append((b.t + ms, 1))
        elif p.c > p.o and b.c < b.o and b.c < p.o and b.o >= p.c:
            out.append((b.t + ms, -1))
    return out


def _at(marks, keys, t):
    i = bisect.bisect_right(keys, t) - 1
    return marks[i][1] if i >= 0 else 0


def _lines(bars, ms):
    """Trendline nga dy swing low ne rritje (+1) dhe nga dy swing high ne renie (-1)."""
    out = []
    lows, highs = [], []
    for c, i, k, v in swings(bars, 3):
        src = lows if k == "L" else highs
        src.append((i, v))
        if len(src) < 2:
            continue
        (i1, v1), (i2, v2) = src[-2], src[-1]
        if i2 - i1 < 5 or (k == "L" and v2 <= v1) or (k == "H" and v2 >= v1):
            continue
        slope = (v2 - v1) / (i2 - i1)
        dead = min(len(bars), i2 + 240)
        for q in range(i2 + 1, dead):
            y = v1 + slope * (q - i1)
            if (k == "L" and bars[q].c < y) or (k == "H" and bars[q].c > y):
                dead = q
                break
        out.append((bars[c].t + ms, 1 if k == "L" else -1, i1, v1, slope, dead))
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
    """Te gjitha hyrjet: dict(t, i, side, entry, sl, tps, tf, combo, near, far, tl, snr)."""
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
    eng = {tf: _engulf_marks(T[tf], ms[tf]) for tf in ("H1", "H4")}
    eng_k = {tf: [x[0] for x in v] for tf, v in eng.items()}
    ctx = {}
    for tf in ("H4", "H1", "M30", "M15"):
        B = T[tf]
        sw = sorted((B[c].t + ms[tf], v) for c, i, k, v in swings(B, 3))
        ctx[tf] = dict(t=[b.t for b in B], atr=atr_series(B, 14), lines=_lines(B, ms[tf]) if tf != "H4" else [],
                       sw=sw, swk=[x[0] for x in sw])
    t1 = [b.t for b in m1]

    def allowed(t, d, tf):
        if _at(trend["D1"], trend_k["D1"], t) != d:
            return None
        for combo, etf, hours, tfs, need_h4 in (("A", "H1", p.h1_engulf_h, COMBO_A, True),
                                               ("B", "H4", p.h4_engulf_h, COMBO_B, False)):
            if tf not in tfs or (need_h4 and _at(trend["H4"], trend_k["H4"], t) != d):
                continue
            k = eng_k[etf]
            for q in range(bisect.bisect_left(k, t - hours * 3_600_000), bisect.bisect_right(k, t)):
                if eng[etf][q][1] == d:
                    return combo
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
                        if not combo or tl + snr < p.need_conf:
                            touched = False              # rejection pa kushtet: pritet prekja tjeter
                            continue
                        sl = far - p.sl_pips if d == 1 else far + p.sl_pips
                        tps = [b.c + d * x_ for x_ in p.tps]
                        out.append(dict(t=t, i=j, side="BUY" if d == 1 else "SELL", entry=b.c, sl=sl, tps=tps,
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
