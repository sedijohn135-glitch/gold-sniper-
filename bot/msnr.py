"""MSNR: SNR Malajzian ne XAUUSD (KororFX / Emperor 7 / SNR Malaysia / Rare SnR), modul i botit.

Nivelet nderohen nga TRUPI i qirinjve H4 dhe D1 (bishtat injorohen):
  A   = qiri bullish pastaj bearish -> rezistence ne mbylljen e te parit
  V   = qiri bearish pastaj bullish -> support ne mbylljen e te parit
  GAP = si A/V, por qiri i dyte mbyllet pertej hapjes se te parit (momentum)
Vetem nivelet ORIGJINALE (jo te flip-uara RBS/SBR) dhe vetem prekja e PARE (fresh), max 30 dite te vjetra.
Kur qiri i TF-se se nivelit mbyllet pertej tij, niveli flip-ohet (RBS/SBR) dhe s'tregtohet me.

Sinjali (SELL; BUY = pasqyra):
  1. Cmimi (M15) prek per here te pare nje rezistence fresh A/GAP te H4/D1.
  2. Brenda 16 qirinjve (4 ore; D1: 16 ore) M15 MBYLLET nen low-in me te ulet te 8 qirinjve (D1: 32) para prekjes
     = thyerje strukture 2 TF me poshte, pa u mbyllur qiri H4/D1 pertej nivelit.
  3. Hyrje ne treg pas mbylljes se qirit te thyerjes; SL 2$ mbi nivel (20 pips, KororFX), TP 4R, SL ne hyrje ne 1R.
Backtest (research/msnr.py, spread 0.20$, 0.01 lot, hyrje 02:00-22:00, mbyllje 22:30, stop pas 2 humbjeve):
  2026 62 trade +253$ DD 93$ | 2016-2025 1564 trade +904$ DD 354$ (8 nga 11 vite pozitive).
"""
from dataclasses import dataclass

M15_MS = 900_000
TF_MS = {"H4": 4 * 3_600_000, "D1": 86_400_000}


@dataclass
class P:
    htf: tuple = ("H4", "D1")
    types: tuple = ("A", "V", "GAP")
    pre: int = 8            # qirinjte M15 para prekjes per strukturen (D1: x4)
    bo_bars: int = 16       # sa qirinj M15 pritet thyerja (D1: x4)
    max_age_d: float = 30
    lbuf: float = 2.0       # SL = niveli + 2$
    rr: float = 4.0
    min_sl: float = 3.0
    max_sl: float = 25.0


class Level:
    __slots__ = ("p", "res", "typ", "tf", "born", "touches", "flips")

    def __init__(self, p, res, typ, tf, born):
        self.p, self.res, self.typ, self.tf, self.born = p, res, typ, tf, born
        self.touches = self.flips = 0


def make_levels(bars, tf_ms, tf):
    out = []
    for i in range(1, len(bars)):
        a, b = bars[i - 1], bars[i]
        if a.c > a.o and b.c < b.o:
            out.append(Level(a.c, True, "GAP" if b.c < a.o else "A", tf, b.t + tf_ms))
        elif a.c < a.o and b.c > b.o:
            out.append(Level(a.c, False, "GAP" if b.c > a.o else "V", tf, b.t + tf_ms))
    return out


def scan(m15, htf_bars, p=P(), k=1.0):
    """Riluan historine M15 dhe kthen cdo sinjal: dict(j = indeksi i qirit M15 te thyerjes, side, level, typ, tf, sl).
    Hyrja eshte ne hapjen e qirit j+1. `htf_bars` = {"H4": [...], "D1": [...]} (qirinj te mbyllur)."""
    lv_all = []
    for tf in p.htf:
        lv_all += make_levels(htf_bars[tf], TF_MS[tf], tf)
    lv_all.sort(key=lambda x: x.born)
    closes = {}
    for tf in p.htf:
        for b in htf_bars[tf]:
            closes.setdefault(b.t + TF_MS[tf], []).append((tf, b))
    max_age = p.max_age_d * 86_400_000
    active, li, setups, out = [], 0, [], []
    for j, b in enumerate(m15):
        end = b.t + M15_MS
        while li < len(lv_all) and lv_all[li].born <= b.t:
            active.append(lv_all[li]); li += 1
        for lv in active:
            if (lv.res and b.h >= lv.p) or (not lv.res and b.l <= lv.p):
                if lv.touches == 0 and lv.flips == 0 and lv.typ in p.types and b.t - lv.born <= max_age:
                    m = 4 if lv.tf == "D1" else 1
                    pre = m15[max(0, j - p.pre * m):j] or [b]
                    setups.append((lv, j, m, min(x.l for x in pre) if lv.res else max(x.h for x in pre)))
                lv.touches += 1
        keep = []
        for lv, j0, m, brk in setups:
            sell = lv.res
            if lv.flips or j - j0 > p.bo_bars * m:
                continue
            if (sell and b.c < brk) or (not sell and b.c > brk):
                sl = lv.p + p.lbuf * k if sell else lv.p - p.lbuf * k
                out.append(dict(j=j, t=b.t, side="SELL" if sell else "BUY", level=lv.p, typ=lv.typ, tf=lv.tf, sl=sl))
                continue
            keep.append((lv, j0, m, brk))
        setups = keep
        for tf, hb in closes.get(end, []):
            for lv in active:
                if lv.tf == tf and lv.born <= hb.t and ((lv.res and hb.c > lv.p) or (not lv.res and hb.c < lv.p)):
                    lv.res = not lv.res
                    lv.typ = "RBS" if not lv.res else "SBR"
                    lv.touches, lv.flips, lv.born = 0, lv.flips + 1, end
            active = [x for x in active if end - x.born <= max_age and x.flips <= 2]
    return out


def signal(m15, htf_bars, p=P(), k=1.0):
    """Sinjali live: vetem nese thyerja ndodhi ne qirin e fundit te mbyllur M15."""
    if not m15:
        return None
    sigs = [s for s in scan(m15, htf_bars, p, k) if s["j"] == len(m15) - 1]
    return sigs[-1] if sigs else None
