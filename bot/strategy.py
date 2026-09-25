"""Zbulimi i majave (tops) dhe fundeve (bottoms) ne XAUUSD M15.

MODE=sniper (fillestar) - lekundjet e dites:
  Ari ben 2-3 maja/funde ne dite. Mesatarja e levizjes ditore (ADR) eshte ~100$
  dhe levizjet mes majave/fundeve te verteta jane >= ~0.45 x ADR (~45$).
  Boti ndjek lekundjet e dites (zigzag qe kthehet pas 0.4 x ADR) dhe kerkon
  refuzim vetem kur leg-u aktual eshte >= 0.45 x ADR nga pivoti i fundit.
  Refuzimi: bisht i gjate, qiri i forte kthimi, ose nje nga 2 qirinjte pas
  ekstremit mbyllet pertej trupit te tij.

MODE=klasik - modeli i vjeter:
  * MAJE -> SELL: qiri ben high me te larte se N qirinjte e meparshem
    (fshin likuiditetin), pas nje ngritjeje te madhe, dhe refuzohet:
    bisht i gjate lart / mbyllje poshte, qiri i forte bearish qe mbyllet ne 25%
    e fundit, ose qiri tjeter mbyllet nen trupin e tij.
  * FUND -> BUY: e njejta gje e kundert.
SL vendoset pertej majes/fundit + buffer ATR, TP = SL x RR.
"""
from dataclasses import dataclass


@dataclass
class Bar:
    t: int      # koha e hapjes, epoch ms
    o: float
    h: float
    l: float
    c: float


@dataclass
class Params:
    lookback: int = 32          # qirinj per maje/fund
    min_leg_atr: float = 3.0    # levizja min para majes/fundit (x ATR)
    min_wick_pct: float = 40.0  # bishti min (% e qirit)
    min_close_pct: float = 50.0 # sa larg ekstremit mbyllet qiri (% e qirit)
    use_rsi: bool = True
    rsi_period: int = 14
    rsi_ob: float = 65.0
    rsi_os: float = 35.0
    atr_period: int = 14
    sl_buffer_atr: float = 0.3
    strong_close_pct: float = 75.0 # qiri i forte kthimi: mbyllet ne 25% e fundit (0 = joaktiv)
    equal_tol_atr: float = 0.0     # maje/fund i dyfishte: lejon ekstremin deri ne kaq ATR nen/mbi te meparshmin
    # --- MODE=sniper (lekundjet e dites) ---
    mode: str = "sniper"           # "sniper" ose "klasik"
    adr_days: int = 10             # ADR = mesatarja e range-it te 10 diteve te fundit
    swing_rev: float = 0.4         # kthimi qe konfirmon nje maje/fund (x ADR)
    leg_min_adr: float = 0.45      # leg-u min para majes/fundit (x ADR)
    confirm_bars: int = 2          # sa qirinj pas ekstremit pranohet konfirmimi


@dataclass
class Signal:
    side: str           # "BUY" ose "SELL"
    extreme: float      # maja ose fundi
    extreme_index: int
    stop_loss: float    # cmimi i SL (para kontrollit min/max)
    atr: float


def atr_series(bars, period):
    """ATR eksponencial (si MovingAverageType.Exponential ne cTrader)."""
    out = [float("nan")] * len(bars)
    alpha = 2.0 / (period + 1)
    ema = None
    for i, b in enumerate(bars):
        tr = b.h - b.l if i == 0 else max(b.h - b.l, abs(b.h - bars[i - 1].c), abs(b.l - bars[i - 1].c))
        ema = tr if ema is None else ema + alpha * (tr - ema)
        if i >= period - 1:
            out[i] = ema
    return out


def rsi_series(bars, period):
    """RSI i Wilder-it mbi cmimet e mbylljes."""
    out = [float("nan")] * len(bars)
    gain = loss = 0.0
    for i in range(1, len(bars)):
        ch = bars[i].c - bars[i - 1].c
        g, lo = max(ch, 0.0), max(-ch, 0.0)
        if i <= period:
            gain += g / period
            loss += lo / period
            if i < period:
                continue
        else:
            gain = (gain * (period - 1) + g) / period
            loss = (loss * (period - 1) + lo) / period
        out[i] = 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)
    return out


def _bearish_rejection(b, p):
    rng = b.h - b.l
    if rng <= 0:
        return False
    upper_wick = b.h - max(b.o, b.c)
    close_pct = (b.h - b.c) / rng * 100
    wick_ok = upper_wick / rng * 100 >= p.min_wick_pct and close_pct >= p.min_close_pct
    strong = p.strong_close_pct > 0 and b.c < b.o and close_pct >= p.strong_close_pct
    return wick_ok or strong


def _bullish_rejection(b, p):
    rng = b.h - b.l
    if rng <= 0:
        return False
    lower_wick = min(b.o, b.c) - b.l
    close_pct = (b.c - b.l) / rng * 100
    wick_ok = lower_wick / rng * 100 >= p.min_wick_pct and close_pct >= p.min_close_pct
    strong = p.strong_close_pct > 0 and b.c > b.o and close_pct >= p.strong_close_pct
    return wick_ok or strong


def detect_classic(bars, i, p: Params, atr, rsi):
    """Modeli klasik: maje/fund i N qirinjve te fundit + RSI."""
    if i < p.lookback + 3:
        return None
    a = atr[i]
    if a != a or a <= 0:  # NaN
        return None

    tol = p.equal_tol_atr * a
    for k in (i, i - 1):
        lo_idx = max(0, k - p.lookback)
        window = bars[lo_idx:k]
        bk = bars[k]

        # ------------- MAJE -> SELL -------------
        if bk.h > max(b.h for b in window) - tol and bk.h >= bars[i].h and bk.h >= bars[i - 1].h:
            leg_low = min(b.l for b in bars[lo_idx:k + 1])
            big_move = bk.h - leg_low >= p.min_leg_atr * a
            rsi_ok = (not p.use_rsi) or max(rsi[k], rsi[k - 1]) >= p.rsi_ob
            if k == i:
                rejected = _bearish_rejection(bk, p)
            else:
                body_low = min(bk.o, bk.c)
                rejected = bars[i].c < bars[i].o and bars[i].c < body_low
            if big_move and rsi_ok and rejected:
                return Signal("SELL", bk.h, k, bk.h + p.sl_buffer_atr * a, a)

        # ------------- FUND -> BUY -------------
        if bk.l < min(b.l for b in window) + tol and bk.l <= bars[i].l and bk.l <= bars[i - 1].l:
            leg_high = max(b.h for b in bars[lo_idx:k + 1])
            big_move = leg_high - bk.l >= p.min_leg_atr * a
            rsi_ok = (not p.use_rsi) or min(rsi[k], rsi[k - 1]) <= p.rsi_os
            if k == i:
                rejected = _bullish_rejection(bk, p)
            else:
                body_high = max(bk.o, bk.c)
                rejected = bars[i].c > bars[i].o and bars[i].c > body_high
            if big_move and rsi_ok and rejected:
                return Signal("BUY", bk.l, k, bk.l - p.sl_buffer_atr * a, a)
    return None


# ---------------------------------------------------------------- MODE=sniper
SERVER_OFFSET_MS = 3 * 3600 * 1000  # dita e grafikut IC Markets = UTC+3


def adr_series(bars, days):
    """Per cdo qiri: mesatarja e range-it (high-low) te `days` diteve te meparshme."""
    out, ranges = [], []
    day = hi = lo = None
    for b in bars:
        d = (b.t + SERVER_OFFSET_MS) // 86_400_000
        if d != day:
            if day is not None:
                ranges.append(hi - lo)
            day, hi, lo = d, b.h, b.l
        else:
            hi, lo = max(hi, b.h), min(lo, b.l)
        last = ranges[-days:]
        out.append(sum(last) / len(last) if len(last) >= 3 else float("nan"))
    return out


def swing_pivots(bars, adr, rev):
    """Zigzag qe shikon vetem te kaluaren: per cdo qiri kthen pivotin e fundit
    te konfirmuar si ("H"/"L", cmimi, indeksi), ose None."""
    out = []
    piv = None
    hi_i = lo_i = None
    for i, b in enumerate(bars):
        a = adr[i]
        if a != a:  # NaN
            out.append(None)
            continue
        if hi_i is None or b.h > bars[hi_i].h:
            hi_i = i
        if lo_i is None or b.l < bars[lo_i].l:
            lo_i = i
        if piv is None or piv[0] == "L":
            # ne leg lart: maja konfirmohet kur cmimi bie rev x ADR nga high-i
            # (qiri qe konfirmon duhet te jete pas ekstremit: brenda nje qiri s'dihet renditja high/low)
            if hi_i < i and bars[hi_i].h - b.l >= rev * a:
                piv = ("H", bars[hi_i].h, hi_i)
                lo_i = i
        if piv is not None and piv[0] == "H" and i > piv[2]:
            # ne leg poshte: fundi konfirmohet kur cmimi ngrihet rev x ADR nga low-i
            if lo_i < i and b.h - bars[lo_i].l >= rev * a:
                piv = ("L", bars[lo_i].l, lo_i)
                hi_i = i
        out.append(piv)
    return out


def detect_swing(bars, i, p: Params, atr, adr, pivots):
    a, day_range, piv = atr[i], adr[i], pivots[i]
    if piv is None or a != a or day_range != day_range:
        return None
    start = piv[2] + 1
    if start > i:
        return None
    for k in range(i, max(start, i - p.confirm_bars) - 1, -1):
        bk = bars[k]
        if piv[0] == "L":
            # leg lart nga fundi i fundit -> kerkojme MAJE (SELL)
            if bk.h < max(b.h for b in bars[start:i + 1]):
                continue
            if bk.h - piv[1] < p.leg_min_adr * day_range:
                continue
            body_low = min(bk.o, bk.c)
            if k == i:
                rejected = _bearish_rejection(bk, p)
            else:
                rejected = bars[i].c < bars[i].o and bars[i].c < body_low and \
                    all(b.c >= body_low for b in bars[k + 1:i])
            if rejected:
                return Signal("SELL", bk.h, k, bk.h + p.sl_buffer_atr * a, a)
        else:
            # leg poshte nga maja e fundit -> kerkojme FUND (BUY)
            if bk.l > min(b.l for b in bars[start:i + 1]):
                continue
            if piv[1] - bk.l < p.leg_min_adr * day_range:
                continue
            body_high = max(bk.o, bk.c)
            if k == i:
                rejected = _bullish_rejection(bk, p)
            else:
                rejected = bars[i].c > bars[i].o and bars[i].c > body_high and \
                    all(b.c <= body_high for b in bars[k + 1:i])
            if rejected:
                return Signal("BUY", bk.l, k, bk.l - p.sl_buffer_atr * a, a)
    return None


def prepare(bars, p: Params):
    """Llogarit treguesit nje here per gjithe listen e qirinjve."""
    atr = atr_series(bars, p.atr_period)
    ind = {"atr": atr, "rsi": rsi_series(bars, p.rsi_period)}
    if p.mode == "sniper":
        ind["adr"] = adr_series(bars, p.adr_days)
        ind["pivots"] = swing_pivots(bars, ind["adr"], p.swing_rev)
    return ind


def detect(bars, i, p: Params, ind=None):
    """Kontrollon qirin e mbyllur `i` per sinjal BUY/SELL."""
    ind = ind or prepare(bars, p)
    if p.mode == "sniper":
        return detect_swing(bars, i, p, ind["atr"], ind["adr"], ind["pivots"])
    return detect_classic(bars, i, p, ind["atr"], ind["rsi"])
