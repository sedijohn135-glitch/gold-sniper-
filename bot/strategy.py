"""Zbulimi i majave (tops) dhe fundeve (bottoms) ne XAUUSD M15.

Ideja (si zonat roze ne screenshot):
  * MAJE -> SELL: qiri ben high me te larte se N qirinjte e meparshem
    (fshin likuiditetin), pas nje ngritjeje te madhe, dhe refuzohet:
    bisht i gjate lart / mbyllje poshte, ose qiri tjeter mbyllet nen trupin e tij.
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
    return upper_wick / rng * 100 >= p.min_wick_pct and (b.h - b.c) / rng * 100 >= p.min_close_pct


def _bullish_rejection(b, p):
    rng = b.h - b.l
    if rng <= 0:
        return False
    lower_wick = min(b.o, b.c) - b.l
    return lower_wick / rng * 100 >= p.min_wick_pct and (b.c - b.l) / rng * 100 >= p.min_close_pct


def detect(bars, i, p: Params, atr=None, rsi=None):
    """Kontrollon qirin e mbyllur `i` (dhe `i-1` si ekstrem) per sinjal."""
    if i < p.lookback + 3:
        return None
    atr = atr or atr_series(bars, p.atr_period)
    rsi = rsi or rsi_series(bars, p.rsi_period)
    a = atr[i]
    if a != a or a <= 0:  # NaN
        return None

    for k in (i, i - 1):
        lo_idx = max(0, k - p.lookback)
        window = bars[lo_idx:k]
        bk = bars[k]

        # ------------- MAJE -> SELL -------------
        if bk.h > max(b.h for b in window) and bk.h >= bars[i].h and bk.h >= bars[i - 1].h:
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
        if bk.l < min(b.l for b in window) and bk.l <= bars[i].l and bk.l <= bars[i - 1].l:
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
