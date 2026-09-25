"""Prototip kerkimi (jo ne botin live): setup-i "trendline 3rd touch" i perdoruesit ne M30.

BUY (SELL eshte pasqyra):
  1. trendline rritese nga dy swing low M30 (L1 < L2), pa asnje mbyllje M30 nen vije mes tyre
  2. prekja e 3-te: nje qiri M30 prek vijen (low <= vija + tol) dhe mbyllet mbi te
  3. pas prekjes, nje M30 mbyllet mbi zonen supply M30 me te afert mbi cmim (thyerje)
  4. retest: nje M30 zbret te zona e thyer dhe mbyllet mbi te me rejection -> hyrje ne mbyllje
  5. SL nen zonen e thyer; TP ne zonen supply M30 me te afert lart (>= min_rr)
Ekzekuto nga rrenja e repo-s: python -m research.trendline3 <m5.pkl>
"""
import sys
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.strategy import adr_series
from research.quasimodo import aggregate, find_zones, swings

M30 = 1_800_000


@dataclass
class P:
    swing_k: int = 2
    min_gap: int = 6            # qirinj M30 minimum mes L1 dhe L2
    max_age: int = 144          # vija vlen per kaq qirinj pas L2 (3 dite)
    touch_tol_adr: float = 0.03 # sa afer vijes duhet te preke (x ADR)
    break_bars: int = 16        # thyerja e zones brenda kaq qirinjve pas prekjes
    retest_bars: int = 16       # retest-i brenda kaq qirinjve pas thyerjes
    retest_tol: float = 1.0     # $
    rej_wick: float = 0.3       # wick-u i rejection-it >= kaq pjese e qirit
    zone_disp: float = 1.5
    sl_buf: float = 0.5
    min_rr: float = 1.5
    max_sl: float = 25.0
    min_sl: float = 1.0
    start_h: int = 1
    end_h: int = 20
    spread: float = 0.2
    close_line: bool = True     # vija nga mbylljet (si ne grafikun "line" te perdoruesit), jo nga wick-et


def run(m5, p: P):
    bars = aggregate(m5, 30)
    adr = adr_series(bars, 10)
    zones = find_zones(bars, M30, p.zone_disp)
    from bot.strategy import Bar
    line_bars = [Bar(x.t, x.c, x.c, x.c, x.c) for x in bars] if p.close_line else bars
    sw = swings(line_bars, p.swing_k)
    conf_at = {}
    for c, i, k, v in sw:
        conf_at.setdefault(c, []).append((i, k, v))
    lows, highs = [], []
    lines = []     # vijat aktive
    trades, pos = [], None
    for j, b in enumerate(bars):
        t_close = b.t + M30
        A = adr[j]
        # --- pozicioni (menaxhim ne M30: konservativ, SL para TP)
        if pos:
            buy = pos["side"] == "BUY"
            lo, hi = (b.l, b.h) if buy else (b.l + p.spread, b.h + p.spread)
            x = pos["sl"] if ((buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"])) else \
                pos["tp"] if ((buy and hi >= pos["tp"]) or (not buy and lo <= pos["tp"])) else None
            if x is not None:
                pos["r"] = ((x - pos["entry"]) if buy else (pos["entry"] - x)) / pos["risk"]
                pos["exit_t"] = b.t
                trades.append(pos)
                pos = None
        # --- swing-et e reja -> vija te reja
        for i, k, v in conf_at.get(j, []):
            (lows if k == "L" else highs).append((i, v))
            src = lows if k == "L" else highs
            if len(src) >= 2:
                (i1, v1), (i2, v2) = src[-2], src[-1]
                rising = v2 > v1
                if i2 - i1 >= p.min_gap and ((k == "L" and rising) or (k == "H" and not rising)):
                    slope = (v2 - v1) / (i2 - i1)
                    ok = all((bars[x].c >= v1 + slope * (x - i1)) if k == "L" else (bars[x].c <= v1 + slope * (x - i1))
                             for x in range(i1, i2 + 1))
                    if ok:
                        lines.append(dict(side="BUY" if k == "L" else "SELL", i1=i1, v1=v1, i2=i2, slope=slope,
                                          touch=None, zone=None, broke=None))
        if A != A:
            continue
        keep = []
        for L in lines:
            buy = L["side"] == "BUY"
            y = L["v1"] + L["slope"] * (j - L["i1"])
            if j - L["i2"] > p.max_age:
                continue
            if j <= L["i2"] + p.swing_k:
                keep.append(L)
                continue
            # vija thyhet -> fund
            if (buy and b.c < y - p.touch_tol_adr * A) or (not buy and b.c > y + p.touch_tol_adr * A):
                continue
            if L["touch"] is None:
                touch_lo = b.c if p.close_line else b.l
                touch_hi = b.c if p.close_line else b.h
                if (buy and touch_lo <= y + p.touch_tol_adr * A and b.c >= y - p.touch_tol_adr * A) or \
                        (not buy and touch_hi >= y - p.touch_tol_adr * A and b.c <= y + p.touch_tol_adr * A):
                    # zona perballe me e afert (supply mbi cmim per BUY)
                    want = "S" if buy else "D"
                    zs = [z for z in zones if z.kind == want and z.known <= t_close < z.dead and
                          ((buy and z.lo > b.c) or (not buy and z.hi < b.c))]
                    if zs:
                        L["touch"] = j
                        L["zone"] = min(zs, key=lambda z: z.lo) if buy else max(zs, key=lambda z: z.hi)
                keep.append(L)
                continue
            z = L["zone"]
            if L["broke"] is None:
                if j - L["touch"] > p.break_bars:
                    continue
                if (buy and b.c > z.hi) or (not buy and b.c < z.lo):
                    L["broke"] = j
                keep.append(L)
                continue
            if j - L["broke"] > p.retest_bars:
                continue
            # zona e thyer humbet kur mbyllet perseri brenda/pertej saj
            if (buy and b.c < z.lo) or (not buy and b.c > z.hi):
                continue
            rng = b.h - b.l
            if buy:
                rej = b.l <= z.hi + p.retest_tol and b.c > z.hi and rng > 0 and (min(b.o, b.c) - b.l) / rng >= p.rej_wick
            else:
                rej = b.h >= z.lo - p.retest_tol and b.c < z.lo and rng > 0 and (b.h - max(b.o, b.c)) / rng >= p.rej_wick
            if not rej or pos is not None or j == L["broke"]:
                keep.append(L)
                continue
            hr = datetime.fromtimestamp(t_close / 1000, timezone.utc)
            if not (p.start_h <= hr.hour < p.end_h) or (hr.weekday() == 4 and hr.hour >= 19):
                keep.append(L)
                continue
            entry = b.c + (p.spread if buy else 0)
            slp = z.lo - p.sl_buf if buy else z.hi + p.sl_buf
            risk = max(abs(entry - slp), p.min_sl)
            if risk > p.max_sl:
                continue
            want = "S" if buy else "D"
            tz = [z2 for z2 in zones if z2.kind == want and z2.known <= t_close < z2.dead and
                  ((buy and z2.lo >= entry + p.min_rr * risk) or (not buy and z2.hi <= entry - p.min_rr * risk))]
            if not tz:
                continue
            tgt = min(z2.lo for z2 in tz) if buy else max(z2.hi for z2 in tz)
            pos = dict(side=L["side"], entry=entry, risk=risk, t=t_close,
                       sl=entry - risk if buy else entry + risk, tp=tgt, zone=(z.lo, z.hi))
        lines = keep
    return trades, sum(t["r"] for t in trades)


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    T, tot = run(m5, P())
    print(len(T), "trade", f"{tot:+.1f}R")

# Rezultati (M5 -> M30 nga llogaria, 26 jan - 25 sht 2026):
#   vija nga wick-et: 17 trade, -7.3R.  Vija nga mbylljet (si grafiku line i perdoruesit):
#   6 trade +0.0R; me prekje 0.06 ADR 16 trade +6.0R; pa kufi wick 10 trade +5.9R.
# Shume pak trade ne 8 muaj per te thene nese ka avantazh. Ne 25 Sep boti zgjodhi zonen
# 4267.68-4277.81 dhe hyri ne 4284 (-1R); perdoruesi hyri ne ~4273 te zona 4269-4272.
