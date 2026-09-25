"""Prototip kerkimi: "truri" i pronarit, sistem pikesh me konfluenca.

SELL (BUY eshte pasqyra), ne cdo qiri M5 me rejection (wick lart, mbyllje ne gjysmen e poshtme):
  koka = maja me e larte e oreve te fundit (P.window_h)

  1. E DETYRUESHME - thyerja LTF: nje zone demand M5/M15/M30 poshte kokes thyhet (mbyllje nen te)
     pas kokes. Ky eshte konfirmimi absolut.
  2. ARSYET HTF te koka (te pakten nje):
       snd   brenda nje zone supply H1/H4
       sbr   brenda nje supporti H1/H4 te thyer (support -> resistance)
       snr   afer nje maje te meparshme H1/H4 (rezistence horizontale)
       tl    prek nje trendline M30/H1 (nga mbylljet; prekja e 3-te)
       qmH   Quasimodo H1: koka mbi left shoulder H1, pastaj mbyllje nen low-in e mesit
       aoH   divergjence AO ne H1 ose H4
  3. KONFLUENCAT LTF:
       ao5 / ao15  divergjence AO ne M5 / M15
       qm5         Quasimodo M5 (kthim te left shoulder)
       sbrL        koka brenda nje supporti M5/M15 te thyer
       tlb         trendline mbeshtetese M30/H1 e thyer pas kokes
       retest      qiri i rejection-it prek zonen e thyer dhe mbyllet poshte saj
       brk2        u thyen zona ne me shume se nje kohe (M5 + M15/M30)
  Pikët = numri i arsyeve HTF + konfluencave LTF. Sa me shume, aq me i forte setup-i.
Hyrja ne mbylljen e qirit, SL pertej wick-ut (min 3$), TP niveli fresh perballe >= 2R.
Ekzekuto nga rrenja e repo-s: python -m research.brain <m5.pkl>
"""
import bisect
import sys
import pickle
from dataclasses import dataclass

from bot.confluence import TF
from bot.hierarchy import ao_series
from bot.strategy import Bar, adr_series
from bot.zones import SRV, aggregate, find_zones, swings, with_flips

HTF_TAGS = ("snd", "sbr", "snr", "tl", "qmH", "aoH")
EXTRA_TAGS = ("fresh", "tlH1", "tlM30")      # hollesi (nuk numerohen ne piket baze)
LTF_TAGS = ("ao5", "ao15", "qm5", "sbrL", "tlb", "retest", "brk2")


@dataclass
class P:
    window_h: float = 8
    disp: float = 1.5
    zone_tol: float = 0.5
    zone_age_days: float = 10
    snr_tol_adr: float = 0.03
    snr_days: float = 10
    tl_tol_adr: float = 0.03
    rej_wick: float = 0.5
    sl_buf: float = 0.5
    max_sl: float = 20.0
    brk_tfs: tuple = ("M1", "M5", "M15", "M30")   # ku kerkohet thyerja LTF (M1 vetem kur jepen qirinjte M1)
    origin_h: float = 12
    tp_buf: float = 1.0


def trendlines(bars, tf_ms, life=144):
    """Trendline nga mbylljet: dy swing (low-e rritese ose high-e zbritese), pa mbyllje pertej vijes.
    `broken` = koha e mbylljes se pare pertej vijes (None nese s'u thye brenda `life` qirinjve)."""
    lb = [Bar(x.t, x.c, x.c, x.c, x.c) for x in bars]
    lines, lows, highs = [], [], []
    for c, i, k, v in swings(lb, 2):
        src = lows if k == "L" else highs
        src.append((i, v))
        if len(src) < 2:
            continue
        (i1, v1), (i2, v2) = src[-2], src[-1]
        if i2 - i1 < 6 or not ((k == "L" and v2 > v1) or (k == "H" and v2 < v1)):
            continue
        slope = (v2 - v1) / (i2 - i1)
        if not all((bars[x].c >= v1 + slope * (x - i1) - 1e-9) if k == "L" else
                   (bars[x].c <= v1 + slope * (x - i1) + 1e-9) for x in range(i1, i2 + 1)):
            continue
        dead, broken = bars[i2].t + life * tf_ms, None
        for x in range(i2 + 1, min(len(bars), i2 + life + 1)):
            y = v1 + slope * (x - i1)
            if (k == "L" and bars[x].c < y) or (k == "H" and bars[x].c > y):
                dead = broken = bars[x].t + tf_ms
                break
        lines.append(dict(kind="D" if k == "L" else "S", t1=bars[i1].t, v1=v1, slope=slope, tf=tf_ms,
                          known=bars[c].t + tf_ms, dead=dead, broken=broken))
    return lines


def _series(m5, minutes, offset=0):
    bars = aggregate(m5, minutes, offset)
    return dict(bars=bars, t=[b.t for b in bars], ao=ao_series(bars), sw=swings(bars, 2), ms=minutes * 60_000)


def _ao_at(h, m5, tm5, i5, t):
    """AO i kohes h ne qirin qe permban kohen t; qiri aktual i pjesshem deri te M5 i5."""
    k = bisect.bisect_right(h["t"], t) - 1
    if k < 34:
        return float("nan"), k
    b = h["bars"][k]
    if b.t + h["ms"] <= m5[i5].t + TF["M5"]:
        return h["ao"][k], k
    lo = bisect.bisect_left(tm5, b.t)
    seg = m5[lo:i5 + 1]
    med = [(x.h + x.l) / 2 for x in h["bars"][k - 33:k]] + [(max(x.h for x in seg) + min(x.l for x in seg)) / 2]
    return sum(med[-5:]) / 5 - sum(med) / 34, k


def prepare(m5, p: P, m1=None):
    S = {"M5": _series(m5, 5), "M15": _series(m5, 15), "M30": _series(m5, 30),
         "H1": _series(m5, 60), "H4": _series(m5, 240, SRV)}
    zones = []
    for tf, s in S.items():
        base = find_zones(s["bars"], TF[tf], p.disp, tf=tf)
        allz = with_flips(base, s["bars"], TF[tf])
        for k, z in enumerate(allz):
            z.flip = k >= len(base)
        zones += allz
    zones.sort(key=lambda z: z.known)
    lines = trendlines(S["M30"]["bars"], TF["M30"]) + trendlines(S["H1"]["bars"], TF["H1"])
    # zonat M1 te thyera (demand M1 i thyer -> supply), vetem per thyerjen LTF
    m1f = []
    if m1:
        base = find_zones(m1, 60_000, p.disp, tf="M1")
        m1f = sorted(with_flips(base, m1, 60_000)[len(base):], key=lambda z: z.known)
    return dict(S=S, zones=zones, lines=lines, adr=adr_series(m5, 10), tm5=[b.t for b in m5],
                m1f=m1f, m1k=[z.known for z in m1f])


def candidates(m5, p: P, ind, start=0):
    S, zones, lines, adr, tm5 = (ind[k] for k in ("S", "zones", "lines", "adr", "tm5"))
    win = int(p.window_h * 12)
    org = int(p.origin_h * 12)
    age = p.zone_age_days * 86_400_000
    snr_ms = p.snr_days * 86_400_000
    conf = {tf: dict(i=0, H=[], L=[]) for tf in S}
    zi = li = 0
    active, act_l = [], []
    lines = sorted(lines, key=lambda L: L["known"])
    out = []
    for i, b in enumerate(m5):
        t_close = b.t + TF["M5"]
        for tf, s in S.items():
            st = conf[tf]
            while st["i"] < len(s["sw"]) and s["bars"][s["sw"][st["i"]][0]].t + s["ms"] <= t_close:
                _, j, k, v = s["sw"][st["i"]]
                st[k].append((j, v))
                st["i"] += 1
        while zi < len(zones) and zones[zi].known <= t_close:
            active.append(zones[zi])
            zi += 1
        while li < len(lines) and lines[li]["known"] <= t_close:
            act_l.append(lines[li])
            li += 1
        if i % 12 == 0:
            active = [z for z in active if z.dead > b.t and b.t - z.known <= age]
            act_l = [L for L in act_l if L["dead"] > b.t - win * TF["M5"]]
        rng = b.h - b.l
        A = adr[i]
        if i < max(start, win) or rng <= 0 or A != A:
            continue
        for side in ("SELL", "BUY"):
            sell = side == "SELL"
            kind, opp = ("S", "D") if sell else ("D", "S")
            if sell:
                rej = (b.h - max(b.o, b.c)) / rng >= p.rej_wick and b.c < (b.h + b.l) / 2
            else:
                rej = (min(b.o, b.c) - b.l) / rng >= p.rej_wick and b.c > (b.h + b.l) / 2
            if not rej:
                continue
            seg = range(i - win, i + 1)
            head_i = max(seg, key=lambda x: m5[x].h) if sell else min(seg, key=lambda x: m5[x].l)
            if head_i == i:
                continue
            head = m5[head_i].h if sell else m5[head_i].l
            ht = m5[head_i].t
            f = set()
            # 1. thyerja LTF (e detyrueshme): zone e kundert e thyer pas kokes -> zone e re "kind"
            brk_tf = set()
            m1z = ind["m1f"][bisect.bisect_right(ind["m1k"], ht):bisect.bisect_right(ind["m1k"], t_close)] \
                if "M1" in p.brk_tfs else []
            for z in active + m1z:
                if z.kind == kind and getattr(z, "flip", True) and z.tf in p.brk_tfs and \
                        ht < z.known <= t_close and z.dead > b.t and ((sell and z.hi < head) or (not sell and z.lo > head)):
                    brk_tf.add(z.tf)
                    if (sell and b.h >= z.lo - 0.5 and b.c <= z.hi) or (not sell and b.l <= z.hi + 0.5 and b.c >= z.lo):
                        f.add("retest")
            if not brk_tf:
                continue
            if len(brk_tf) > 1:
                f.add("brk2")
            # 2. arsyet HTF + sbrL te koka
            for z in active:
                if z.kind != kind or z.known > ht or z.dead <= b.t or not (z.lo - p.zone_tol <= head <= z.hi + p.zone_tol):
                    continue
                flip = getattr(z, "flip", False)
                if z.tf in ("H1", "H4"):
                    f.add("sbr" if flip else "snd")
                    if z.first_touch >= m5[i - win].t - TF[z.tf]:
                        f.add("fresh")          # prekja e pare e zones H1/H4 ne kete levizje
                elif flip and z.tf in ("M5", "M15"):
                    f.add("sbrL")
            for tf in ("H1", "H4"):
                s, st = S[tf], conf[tf]
                kh = bisect.bisect_right(s["t"], ht) - 1
                src = st["H"] if sell else st["L"]
                k0 = bisect.bisect_left(src, (kh - 1, -1e18)) - 1      # swing-et para qirit te kokes
                tol = p.snr_tol_adr * A
                for x in range(k0, max(-1, k0 - 30), -1):
                    j, v = src[x]
                    if ht - s["t"][j] > snr_ms:
                        break
                    if abs(v - head) <= tol:
                        f.add("snr")
                        break
                if k0 >= 0 and kh - src[k0][0] <= (60 if tf == "H1" else 30):
                    j, v = src[k0]
                    a_head, _ = _ao_at(s, m5, tm5, head_i, ht)
                    if a_head == a_head and s["ao"][j] == s["ao"][j] and (
                            (sell and head > v and a_head < s["ao"][j]) or (not sell and head < v and a_head > s["ao"][j])):
                        f.add("aoH")
                    if tf == "H1" and ((sell and v < head) or (not sell and v > head)):
                        mids = st["L"] if sell else st["H"]
                        mm = [w for jj, w in mids if j < jj < kh]
                        if mm:
                            mid = min(mm) if sell else max(mm)
                            after = m5[head_i + 1:i + 1]
                            if (sell and min(x.c for x in after) < mid) or (not sell and max(x.c for x in after) > mid):
                                f.add("qmH")
            for L in act_l:
                if L["known"] > ht or L["dead"] <= ht:
                    continue
                y = L["v1"] + L["slope"] * (ht - L["t1"]) / L["tf"]
                if L["kind"] == kind and abs(head - y) <= p.tl_tol_adr * A:
                    f.add("tl")
                    f.add("tlH1" if L["tf"] == TF["H1"] else "tlM30")
                if L["kind"] == opp and L["broken"] and ht < L["broken"] <= t_close:
                    f.add("tlb")
            if not f & set(HTF_TAGS):
                continue
            # 3. konfluencat LTF: AO M5/M15, QM M5
            for tf, tag in (("M5", "ao5"), ("M15", "ao15")):
                s, st = S[tf], conf[tf]
                kh = bisect.bisect_right(s["t"], ht) - 1
                src = st["H"] if sell else st["L"]
                k0 = bisect.bisect_left(src, (kh, -1e18)) - 1
                if k0 >= 0 and kh - src[k0][0] <= 48:
                    j, v = src[k0]
                    a_head, _ = _ao_at(s, m5, tm5, head_i, ht)
                    if a_head == a_head and s["ao"][j] == s["ao"][j] and (
                            (sell and head > v and a_head < s["ao"][j]) or (not sell and head < v and a_head > s["ao"][j])):
                        f.add(tag)
            st = conf["M5"]
            mids = st["L"] if sell else st["H"]
            k1 = bisect.bisect_left(mids, (head_i, -1e18)) - 1
            if k1 >= 0:
                mj, mv = mids[k1]
                after = m5[head_i + 1:i + 1]
                if (sell and min(x.c for x in after) < mv) or (not sell and max(x.c for x in after) > mv):
                    sh = st["H"] if sell else st["L"]
                    k2 = bisect.bisect_left(sh, (mj, -1e18)) - 1
                    if k2 >= 0:
                        ls = sh[k2][1]
                        if (sell and ls < head and b.h >= ls - 1.0) or (not sell and ls > head and b.l <= ls + 1.0):
                            f.add("qm5")
            sl = b.h + p.sl_buf if sell else b.l - p.sl_buf
            if abs(b.c - sl) > p.max_sl:
                continue
            near = [(z.hi if sell else z.lo) for z in active if z.kind == opp and z.tf != "M5" and z.dead > b.t
                    and z.first_touch >= b.t - TF[z.tf] + TF["M5"]]
            near += [L["v1"] + L["slope"] * (b.t - L["t1"]) / L["tf"] for L in act_l
                     if L["kind"] == opp and L["known"] <= t_close < L["dead"]]
            near = sorted((c for c in near if (sell and c < b.c) or (not sell and c > b.c)), key=lambda c: abs(c - b.c))
            o_seg = m5[max(0, head_i - org):head_i + 1]
            origin = (min(x.l for x in o_seg) + p.tp_buf) if sell else (max(x.h for x in o_seg) - p.tp_buf)
            out.append(dict(i=i, t=t_close, side=side, entry_c=b.c, sl=sl, risk=abs(b.c - sl), feats=frozenset(f),
                            brk=sorted(brk_tf), tps=near, origin=origin, head=head))
    return out


def score(c):
    return len(c["feats"] & set(HTF_TAGS)) + len(c["feats"] & set(LTF_TAGS))


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    p = P()
    C = candidates(m5, p, prepare(m5, p))
    print(len(C), "kandidate")

# Rezultati (M5 nga llogaria, 26 jan - 25 sht 2026); SL >= 3$, TP >= 2R, nje pozicion njeheresh.
# Koka 4/8/12 ore, wick 0.4/0.5, TP "near" (niveli fresh perballe) ose "origin" (fillimi i leg-ut).
# 1. Piket e thjeshta NUK rriten bashke me fitimin. Koka 8h, mesatarja per kandidat (near):
#      1: +0.21R | 2: -0.13 | 3: -0.32 | 4: -0.05 | 5: -0.07 | 6: +0.14 | 7+: -0.09
#    Tregtimi me piket >= K humb per K = 1-5 ne cdo variant; K >= 6 ndryshon shenje sipas variantit.
# 2. Cdo konfluence vec e veç (koka 8h, near; me / pa tag, shk-maj / qer-sht):
#      tl (trendline M30/H1 te koka) +1.31/+0.34 kundrejt -0.15/-0.05  <- me e forta
#      snd (zone H1/H4)              -0.01/+0.07 kundrejt -0.23/-0.12
#      ao5, ao15, aoH, qm5, qmH, retest, sbrL, brk2: te perziera ose pa ndikim.
# 3. Peshat e mesuara ne njeren periudhe dhe te testuara ne tjetren: TEST negativ ne 15 nga 16 raste.
# 4. Kombinimi tl + snd: pozitiv ne 8/8 variante dhe ne te dy periudhat ne secilin
#    (koka 8h, near: 23 trade, 7 fitime, +34.0R, DD 4.0R; shk-maj +22.9R, qer-sht +11.0R), por
#    3 trade-t me te mira japin 32.4R (31 mars +17.2R). Shume pak trade per botin live.
# 5. Thyerja ne M1 (qirinjte M1 nga cTrader: bot.data.fetch_bars(..., "M_1"), 237 274 qirinj):
#    shembulli i 25 shtatorit (demand M1 i thyer -> supply M5) kapet: SELL 16:10 UTC @ 4293.95,
#    SL 4300.84, thyerje M1+M5+M15+M30, 8 konfluenca (piket me te larta).
#    Por kandidatet ku thyhet VETEM M1 (pa M5/M15/M30) humbin ne cdo variant: TP near -90R deri
#    -143R, TP origin -77R deri -122R. M1 thyhet pothuajse gjithmone (9 617 nga 9 716 kandidate),
#    prandaj vete s'eshte konfirmim. Te tl + snd, trade-t shtese vetem-M1: 12 trade, -5.3R.
#    Konfirmimi absolut mbetet thyerja ne M5/M15/M30; M1 ndihmon vetem kur thyhen edhe keto.
