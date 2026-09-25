"""Prototip kerkimi (jo ne botin live): strategjia e perdoruesit
H1 supply/demand + M5 Quasimodo (HH/LL + thyerje strukture) + divergjence AO,
hyrje ne rikthimin te left shoulder me rejection ne M5, SL mbi rejection, TP te zona M15 perballe.
"""
import collections
from dataclasses import dataclass, field
from datetime import datetime, timezone


from bot.strategy import Bar, atr_series  # ekzekuto nga rrenja e repo-s: python -m research.quasimodo


def aggregate(m5, minutes):
    ms = minutes * 60_000
    out, cur, key = [], None, None
    for b in m5:
        k = b.t // ms
        if k != key:
            if cur: out.append(cur)
            key = k
            cur = Bar(k * ms, b.o, b.h, b.l, b.c)
        else:
            cur = Bar(cur.t, cur.o, max(cur.h, b.h), min(cur.l, b.l), b.c)
    if cur: out.append(cur)
    return out


@dataclass
class Zone:
    kind: str      # "S" supply, "D" demand
    lo: float
    hi: float
    known: int     # koha (ms) kur zona njihet (mbyllja e qirinjve te levizjes)
    dead: int = 2**62  # koha kur zona prishet (mbyllje pertej saj)
    touches: int = 0


def find_zones(bars, tf_ms, disp=1.5, look=3, atr_n=14):
    atr = atr_series(bars, atr_n)
    zones = []
    for j in range(atr_n, len(bars) - look):
        a = atr[j]
        if a != a: continue
        b = bars[j]
        nxt = bars[j + 1:j + 1 + look]
        # supply: nga baza (j) renie e forte
        if min(x.l for x in nxt) <= b.l - disp * a and b.h >= max(x.h for x in bars[j + 1:j + 2]):
            z = Zone("S", min(b.o, b.c), max(b.h, nxt[0].h), bars[j + look].t + tf_ms)
            zones.append(z)
        if max(x.h for x in nxt) >= b.h + disp * a and b.l <= min(x.l for x in bars[j + 1:j + 2]):
            z = Zone("D", min(b.l, nxt[0].l), max(b.o, b.c), bars[j + look].t + tf_ms)
            zones.append(z)
    # prishja: mbyllje e nje qiri pertej zones pasi njihet
    for z in zones:
        for x in bars:
            if x.t + tf_ms <= z.known: continue
            if (z.kind == "S" and x.c > z.hi) or (z.kind == "D" and x.c < z.lo):
                z.dead = x.t + tf_ms
                break
    return zones


def ao_series(bars):
    med = [(b.h + b.l) / 2 for b in bars]
    out = [float("nan")] * len(bars)
    s5 = s34 = 0.0
    for i, m in enumerate(med):
        s5 += m; s34 += m
        if i >= 5: s5 -= med[i - 5]
        if i >= 34: s34 -= med[i - 34]
        if i >= 33: out[i] = s5 / 5 - s34 / 34
    return out


def swings(bars, k=2):
    """pikat swing te konfirmuara: (indeksi i konfirmimit, indeksi, 'H'/'L', cmimi)"""
    out = []
    for i in range(k, len(bars) - k):
        h, l = bars[i].h, bars[i].l
        if all(h > bars[i - d].h for d in range(1, k + 1)) and all(h >= bars[i + d].h for d in range(1, k + 1)):
            out.append((i + k, i, "H", h))
        if all(l < bars[i - d].l for d in range(1, k + 1)) and all(l <= bars[i + d].l for d in range(1, k + 1)):
            out.append((i + k, i, "L", l))
    out.sort()
    return out


@dataclass
class P:
    disp_h1: float = 1.5
    disp_m15: float = 1.5
    zone_tol: float = 0.5       # $: sa jashte zones lejohet koka
    swing_k: int = 2
    use_ao: bool = True
    lvl_tol: float = 1.0        # $: sa afer left shoulder duhet te vije cmimi
    expire_bars: int = 48       # M5 qirinj pas thyerjes (4 ore)
    sl_buf: float = 0.5         # $ mbi rejection
    sl_mode: str = "rej"        # "rej" = mbi qirin e rejection, "head" = mbi koken
    min_rr: float = 2.0         # TP te zona duhet te jete >= kaq R
    fallback_rr: float = 0.0    # nese s'ka zone: >0 TP ne kaq R, 0 = skip
    max_sl: float = 15.0
    min_sl: float = 1.0
    be_r: float = 0.0           # break-even pas kaq R (0 = jo)
    start_h: int = 1
    end_h: int = 20
    spread: float = 0.2
    max_zone_age_days: float = 10
    rej_mode: str = "confirm"   # "strict": qiri qe prek eshte rejection; "confirm": prekje, pastaj qiri bearish nen te
    confirm_bars: int = 2
    tp_mode: str = "origin"     # "near": zona M15 me e afert (>= min_rr); "origin": fundi/maja nga nisi leg-u; "rr"
    origin_bars: int = 144      # sa qirinj M5 mbrapa kerkohet origjina e leg-ut (12 ore)
    tp_buf: float = 1.0         # $ para origjines


def prepare(m5, p: P):
    m15 = aggregate(m5, 15); h1 = aggregate(m5, 60)
    zh1 = find_zones(h1, 3_600_000, p.disp_h1)
    zm15 = find_zones(m15, 900_000, p.disp_m15)
    return dict(m15=m15, h1=h1, zh1=zh1, zm15=zm15, ao=ao_series(m5), sw=swings(m5, p.swing_k))


def active(zones, kind, t, max_age_ms):
    return [z for z in zones if z.kind == kind and z.known <= t < z.dead and t - z.known <= max_age_ms]


def run(m5, p: P, ind=None, verbose=False):
    ind = ind or prepare(m5, p)
    ao, sw = ind["ao"], ind["sw"]
    age = p.max_zone_age_days * 86_400_000
    trades = []
    pos = None
    setups = []            # setup-et aktive: dict
    sw_hist = []           # swing-et e konfirmuara deri tani
    si = 0
    for i, b in enumerate(m5):
        # --- menaxho pozicionin
        if pos:
            buy = pos["side"] == "BUY"
            lo, hi = (b.l, b.h) if buy else (b.l + p.spread, b.h + p.spread)
            x = None
            if (buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"]): x = pos["sl"]
            elif (buy and hi >= pos["tp"]) or (not buy and lo <= pos["tp"]): x = pos["tp"]
            if x is not None:
                pos["r"] = ((x - pos["entry"]) if buy else (pos["entry"] - x)) / pos["risk"]
                pos["exit_t"] = b.t
                trades.append(pos); pos = None
            elif p.be_r > 0:
                fav = (hi - pos["entry"]) if buy else (pos["entry"] - lo)
                if fav >= p.be_r * pos["risk"]:
                    pos["sl"] = max(pos["sl"], pos["entry"]) if buy else min(pos["sl"], pos["entry"])
        # --- swing-et e reja te konfirmuara ne kete qiri
        while si < len(sw) and sw[si][0] <= i:
            sw_hist.append(sw[si]); si += 1
            c = sw_hist[-1]
            # kerko QM: per SELL koka = swing H me i larte se H i meparshem, me nje L ne mes
            hs = [s for s in sw_hist[-8:] if s[2] == "H"]
            ls = [s for s in sw_hist[-8:] if s[2] == "L"]
            if c[2] == "H" and len(hs) >= 2:
                head, sh = hs[-1], hs[-2]
                mids = [s for s in ls if sh[1] < s[1] < head[1]]
                if head[3] > sh[3] and mids:
                    low1 = min(mids, key=lambda s: s[3])
                    zs = active(ind["zh1"], "S", m5[head[1]].t, age)
                    if any(z.lo - p.zone_tol <= head[3] <= z.hi + p.zone_tol for z in zs):
                        if not p.use_ao or (ao[head[1]] == ao[head[1]] and ao[sh[1]] == ao[sh[1]] and ao[head[1]] < ao[sh[1]]):
                            orig = min(m5[j].l for j in range(max(0, head[1] - p.origin_bars), head[1] + 1))
                            setups.append(dict(side="SELL", head=head[3], lvl=sh[3], brk=low1[3], born=i, broken=None, used=False, orig=orig, touch=None))
            if c[2] == "L" and len(ls) >= 2:
                head, sh = ls[-1], ls[-2]
                mids = [s for s in hs if sh[1] < s[1] < head[1]]
                if head[3] < sh[3] and mids:
                    high1 = max(mids, key=lambda s: s[3])
                    zs = active(ind["zh1"], "D", m5[head[1]].t, age)
                    if any(z.lo - p.zone_tol <= head[3] <= z.hi + p.zone_tol for z in zs):
                        if not p.use_ao or (ao[head[1]] == ao[head[1]] and ao[sh[1]] == ao[sh[1]] and ao[head[1]] > ao[sh[1]]):
                            orig = max(m5[j].h for j in range(max(0, head[1] - p.origin_bars), head[1] + 1))
                            setups.append(dict(side="BUY", head=head[3], lvl=sh[3], brk=high1[3], born=i, broken=None, used=False, orig=orig, touch=None))
        # --- perditeso setup-et: thyerja, anulimi, hyrja
        keep = []
        for s in setups:
            sell = s["side"] == "SELL"
            if (sell and b.h > s["head"]) or (not sell and b.l < s["head"]):
                continue  # koka u thye: QM i pavlefshem
            if s["broken"] is None:
                if (sell and b.c < s["brk"]) or (not sell and b.c > s["brk"]):
                    s["broken"] = i
                if i - s["born"] > p.expire_bars: continue
                keep.append(s); continue
            if i - s["broken"] > p.expire_bars: continue
            # rikthim te left shoulder + rejection
            touched = (b.h >= s["lvl"] - p.lvl_tol) if sell else (b.l <= s["lvl"] + p.lvl_tol)
            rng = b.h - b.l
            if touched:
                s["touch"] = i
                s["ext"] = max(s.get("ext", b.h), b.h) if sell else min(s.get("ext", b.l), b.l)
            rej = False
            if rng > 0 and touched and p.rej_mode in ("strict", "confirm"):
                if sell: rej = b.c < b.o and b.c < s["lvl"] and (b.h - b.c) / rng >= 0.5
                else: rej = b.c > b.o and b.c > s["lvl"] and (b.c - b.l) / rng >= 0.5
            if not rej and p.rej_mode == "confirm" and s["touch"] is not None and 0 < i - s["touch"] <= p.confirm_bars:
                tb = m5[s["touch"]]
                if sell: rej = b.c < b.o and b.c < tb.l
                else: rej = b.c > b.o and b.c > tb.h
            if rej:
                if pos is None and i + 1 < len(m5):
                    nb = m5[i + 1]
                    hr = datetime.fromtimestamp(nb.t / 1000, timezone.utc)
                    if p.start_h <= hr.hour < p.end_h and not (hr.weekday() == 4 and hr.hour >= 19):
                        entry = nb.o + (p.spread if not sell else 0)
                        rej_ext = max(b.h, s.get("ext", b.h)) if sell else min(b.l, s.get("ext", b.l))
                        slp = (rej_ext + p.sl_buf if sell else rej_ext - p.sl_buf) if p.sl_mode == "rej" else \
                              (s["head"] + p.sl_buf if sell else s["head"] - p.sl_buf)
                        risk = max(abs(entry - slp), p.min_sl)
                        if risk <= p.max_sl and ((sell and entry < slp) or (not sell and entry > slp)):
                            zs = active(ind["zm15"], "D" if sell else "S", b.t, age)
                            tgt = None
                            if sell:
                                c2 = [z.hi for z in zs if z.hi < entry - p.min_rr * risk]
                                tgt = max(c2) if c2 else None
                            else:
                                c2 = [z.lo for z in zs if z.lo > entry + p.min_rr * risk]
                                tgt = min(c2) if c2 else None
                            if p.tp_mode == "origin":
                                o = s["orig"] + p.tp_buf if sell else s["orig"] - p.tp_buf
                                tgt = o if ((sell and o < entry - p.min_rr * risk) or (not sell and o > entry + p.min_rr * risk)) else None
                            elif p.tp_mode == "rr":
                                tgt = None
                            if tgt is None and p.fallback_rr > 0:
                                tgt = entry - p.fallback_rr * risk if sell else entry + p.fallback_rr * risk
                            if tgt is not None:
                                pos = dict(side=s["side"], entry=entry, risk=risk, t=nb.t,
                                           sl=entry + risk if sell else entry - risk, tp=tgt,
                                           head=s["head"], lvl=s["lvl"])
                                continue  # setup-i u perdor
            keep.append(s)
        setups = keep
    return trades, sum(t["r"] for t in trades)


# Rezultati (M5 nga llogaria, 26 jan - 25 sht 2026), P(swing_k=2, disp_h1=1.5, use_ao=False,
# sl_mode="rej", tp_mode="origin"): 109 trade, 16% fitime, +20.8R (shk-maj +7.2R, qer-sht +13.6R).
# Me filtrin AO mbeten vetem 7-8 trade ne 8 muaj. Si modul i dyte krahas botit: +171R por
# drawdown 28R (nga 21R) dhe korriku -10.5R, prandaj nuk u shtua ne botin live.
