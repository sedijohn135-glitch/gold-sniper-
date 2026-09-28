"""ZONA SNIPER: setup-i i pronarit (shembujt 22-25 shtator 2026, XAUUSD).

BUY:
  1. M15: DBD. Qiri i fundit bullish i bazes; zona = hija e tij nga open deri te low.
  2. Rally qe e thyen paster: mbyllje M15 mbi majen e atij qiriri, me trup >= 50% (SBR ne te majte).
  3. Engulfing bullish i mbyllur ne M30, H1 ose H4, nga 4 ore para thyerjes deri ne hyrje.
  4. Prekja e pare e zones -> rejection M15 (mbyllje mbi zone brenda 1 ore) -> BUY ne mbyllje.
     SL nen bishtin me te ulet te retest-it - 0.5 ATR(M15); TP = 2R, minimumi 10$ (100 pips).
  5. Kur zona deshton (mbyllje M15 >= 0.25 ATR nen zone), behet rezistence: prekja e pare nga poshte ->
     rejection M15 -> SELL (kunder), pa kushtin e engulfing-ut.
SELL: pasqyra (RBR, hija e siperme e qiririt bearish nga open deri te high).

`entries(m5, p)` jep te gjitha hyrjet ne seri (per backtest); `signal(m5, p)` vetem hyrjen ne qirin e fundit.
"""
import bisect
from dataclasses import dataclass, replace

from .strategy import Bar, atr_series
from .zones import aggregate

M5 = 300_000
M15 = 900_000


@dataclass
class P:
    rr: float = 2.0            # TP ne R
    min_tp: float = 10.0       # TP minimal ne $ (100 pips)
    sl_buf: float = 0.5        # SL pertej bishtit, ne ATR M15 (retest-et zbresin 2-6$ nen zone)
    touch_bars: int = 4        # rejection-i pritet deri 1 ore pas prekjes (qirinj M15)
    fail_atr: float = 0.25     # zona deshton me mbyllje M15 >= 0.25 ATR pertej saj
    engulf_h: float = 4.0      # engulfing-u HTF: nga 4 ore para thyerjes
    max_age_d: float = 5.0     # zona vlen 5 dite
    engulf: bool = True
    flip: bool = True


USD_FIELDS = ("min_tp",)


def scaled(p: P, k: float) -> P:
    return replace(p, **{f: getattr(p, f) * k for f in USD_FIELDS})


def _mirror(bars):
    return [Bar(b.t, -b.o, -b.l, -b.h, -b.c) for b in bars]


def _closed(bars, tf_ms, last_close):
    """Vetem qirinjte e mbyllur (qiri i fundit i pambyllur hiqet)."""
    return [b for b in bars if b.t + tf_ms <= last_close]


def _zones(b15, atr):
    """Zonat BUY (ne cmime te pasqyruara per SELL): (lo, hi, koha e thyerjes, atr, koha e bazes)."""
    out = []
    n = len(b15)
    for j in range(9, n - 2):
        x = atr[j]
        if x != x or x <= 0:
            continue
        base = b15[j]
        if not base.c > base.o or base.h - base.l > 1.5 * x or base.o - base.l <= 0:
            continue
        if max(b15[q].h for q in range(j - 8, j)) - base.l < 1.5 * x:
            continue
        lo_i = next((q for q in range(j + 1, min(j + 5, n)) if b15[q].c < base.l and base.c - b15[q].c >= 1.0 * x),
                    None)
        if lo_i is None:
            continue
        for q in range(lo_i + 1, min(lo_i + 200, n)):
            b = b15[q]
            if b.c > base.h:
                rng = b.h - b.l
                if rng > 0 and b.c > b.o and (b.c - b.o) >= 0.5 * rng:
                    out.append((base.l, base.o, b.t + M15, x, base.t))
                break
    return out


def _engulfs(bars, last_close):
    """Kohet e mbylljes se engulfing-eve bullish ne M30, H1, H4 (nga M5)."""
    out = []
    for mins in (30, 60, 240):
        ms = mins * 60_000
        B = _closed(aggregate(bars, mins), ms, last_close)
        out += [b.t + ms for p, b in zip(B, B[1:]) if p.c < p.o and b.c > b.o and b.c > p.o and b.o <= p.c]
    return sorted(out)


def _side_entries(m5, p, buy):
    """Hyrjet per njeren ane (m5 i pasqyruar per SELL). Prekja, rejection-i dhe deshtimi shihen ne
    mbylljet M15, si ne grafikun e pronarit; `i` = indeksi i qiririt M5 qe mbyllet bashke me M15."""
    last_close = m5[-1].t + M5
    b15 = _closed(aggregate(m5, 15), M15, last_close)
    atr = atr_series(b15, 14)
    eng = _engulfs(m5, last_close)
    t5 = [b.t for b in m5]
    t15 = [b.t for b in b15]
    out = []
    for lo, hi, known, x, tbase in _zones(b15, atr):
        k = bisect.bisect_left(t15, known)
        end = bisect.bisect_left(t15, known + p.max_age_d * 86_400_000)
        stage, touch, done = "zone", None, False
        while k < min(end, len(b15)) and not done:
            b = b15[k]
            close_t = b.t + M15
            i5 = bisect.bisect_left(t5, close_t - M5)
            if stage == "zone":
                if touch is None:
                    if b.l > hi:
                        k += 1
                        continue
                    touch, ext = k, b.l
                ext = min(ext, b.l)
                if b.c < lo - p.fail_atr * x:                   # zona deshtoi: mbyllje M15 poshte saj
                    if not p.flip:
                        break
                    stage, touch = "flip", None
                    k += 1
                    continue
                if touch >= 0 and b.c > hi:
                    if k - touch <= p.touch_bars:
                        lo_e = bisect.bisect_left(eng, known - p.engulf_h * 3_600_000)
                        if not p.engulf or (lo_e < len(eng) and eng[lo_e] <= close_t):
                            out.append(dict(i=i5, side="BUY" if buy else "SELL", entry=b.c,
                                            sl=min(ext, lo) - p.sl_buf * x, lo=lo, hi=hi, kind="zone", atr=x))
                    touch = -1                                   # vetem prekja e pare; pastaj pritet deshtimi
                k += 1
                continue
            # zona u be rezistence: prekja e pare nga poshte -> rejection -> kunder
            if touch is None:
                if b.h < lo:
                    k += 1
                    continue
                touch, ext = k, b.h
            ext = max(ext, b.h)
            if b.c > hi + p.fail_atr * x or k - touch > p.touch_bars:
                break
            if b.c < lo:
                out.append(dict(i=i5, side="SELL" if buy else "BUY", entry=b.c,
                                sl=max(ext, hi) + p.sl_buf * x, lo=lo, hi=hi, kind="flip", atr=x))
                done = True
            k += 1
    return out


def entries(m5, p: P):
    """Te gjitha hyrjet: dict(i, side, entry, sl, tp, kind, lo, hi) ne cmimet reale."""
    out = []
    for buy, bars in ((True, m5), (False, _mirror(m5))):
        for e in _side_entries(bars, p, buy):
            if not buy:
                e = dict(e, entry=-e["entry"], sl=-e["sl"], lo=-e["hi"], hi=-e["lo"])
            long = e["side"] == "BUY"
            risk = abs(e["entry"] - e["sl"])
            if risk <= 0:
                continue
            d = max(p.rr * risk, p.min_tp)
            e["tp"] = e["entry"] + d if long else e["entry"] - d
            e["risk"] = risk
            out.append(e)
    return sorted(out, key=lambda e: e["i"])


def signal(m5, p: P):
    """Hyrja ne mbylljen e qiririt te fundit M5, ose None."""
    last = len(m5) - 1
    for e in entries(m5, p):
        if e["i"] == last:
            return e
    return None
