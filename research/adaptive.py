"""Prototip kerkimi: motori adaptiv i pronarit.

Boti shikon vete kontekstin ne H1 dhe H4 dhe pastaj kerkon trigger-in ne M5. SELL (BUY pasqyra):

KONTEKSTI (te koka = maja me e larte e 8 oreve te fundit)
  zH1 / zH4    koka brenda nje zone supply H1 / H4 te pathyer (cfaredo prekje)
  zH1f / zH4f  e njejta, por kjo eshte prekja e pare e zones (fresh)
  sbr          koka brenda nje supporti M15/H1 te thyer (support -> resistance)
  dH1 / dH4    divergjence AO ne H1 / H4: koka mbi swing high-in e meparshem, AO me i ulet
TRIGGER-I (M5)
  bos          mbyllje nen swing low-in e fundit para kokes (demand-i i fundit M5 i thyer)
  flip         rejection-i prek demand-in M5 te thyer (SBR / RBS), fresh
  ao           divergjence AO ne M5 te koka
  (+ qm, tl, ltf si ne bot/hierarchy.py)
HYRJA: qiri M5 rejection, hyrje ne mbyllje, SL pertej wick-ut (min 3$).
TP: "near" = niveli fresh perballe (M15+ ose trendline); "origin" = fillimi i leg-ut qe solli
cmimin te koka (low-i me i ulet i 12 oreve para saj), si demand-i M15 ne shembullin e 24 shtatorit.
Ekzekuto nga rrenja e repo-s: python -m research.adaptive <m5.pkl>
"""
import bisect
import sys
import pickle
from dataclasses import dataclass

from bot.confluence import TF
from bot.hierarchy import ao_series, prepare as h_prepare, P as HP
from bot.zones import SRV, aggregate, swings

CTX = ("zH1", "zH1f", "zH4", "zH4f", "sbr", "dH1", "dH4")
TRG = ("bos", "flip", "ao", "qm", "tl", "ltf")


@dataclass
class P:
    window_h: float = 8          # koka = maja/fundi i ketyre oreve te fundit
    zone_tol: float = 0.5
    rej_wick: float = 0.5
    sl_buf: float = 0.5
    div_look: dict = None        # sa qirinj HTF mbrapa per swing-un e divergjences
    origin_h: float = 12
    tp_buf: float = 1.0
    zone_age_days: float = 10
    max_sl: float = 20.0

    def __post_init__(self):
        self.div_look = self.div_look or {"H1": 60, "H4": 30}


def _htf(m5, minutes, offset=0):
    bars = aggregate(m5, minutes, offset)
    return dict(bars=bars, t=[b.t for b in bars], ao=ao_series(bars), sw=swings(bars, 2),
                ms=minutes * 60_000)


def _ao_at(h, m5, i5, t):
    """AO i kohes se larte ne qirin HTF qe permban kohen t, me qirin aktual te pjesshem deri te M5 i5."""
    k = bisect.bisect_right(h["t"], t) - 1
    if k < 34:
        return float("nan")
    b = h["bars"][k]
    if b.t + h["ms"] <= m5[i5].t + TF["M5"]:
        return h["ao"][k]
    lo = bisect.bisect_left(h["tm5"], b.t)
    hi_, lo_ = max(x.h for x in m5[lo:i5 + 1]), min(x.l for x in m5[lo:i5 + 1])
    med = [(x.h + x.l) / 2 for x in h["bars"][k - 33:k]] + [(hi_ + lo_) / 2]
    return sum(med[-5:]) / 5 - sum(med) / 34


def prepare(m5, p: P):
    ind = h_prepare(m5, HP(htf=()))
    ind["H1"], ind["H4"] = _htf(m5, 60), _htf(m5, 240, SRV)
    tm5 = [b.t for b in m5]
    for k in ("H1", "H4"):
        ind[k]["tm5"] = tm5
    return ind


def candidates(m5, p: P, ind):
    zones, lines, adr, ao, sw = (ind[k] for k in ("zones", "lines", "adr", "ao", "sw"))
    win = int(p.window_h * 12)
    org = int(p.origin_h * 12)
    age = p.zone_age_days * 86_400_000
    his, los = [], []
    si = zi = 0
    active = []
    hsw = {k: dict(i=0, H=[], L=[]) for k in ("H1", "H4")}
    out = []
    for i, b in enumerate(m5):
        t_close = b.t + TF["M5"]
        while si < len(sw) and sw[si][0] <= i:
            _, j, k, v = sw[si]
            (his if k == "H" else los).append((j, v))
            si += 1
        for tf in ("H1", "H4"):
            h, st = ind[tf], hsw[tf]
            while st["i"] < len(h["sw"]) and h["bars"][h["sw"][st["i"]][0]].t + h["ms"] <= t_close:
                _, j, k, v = h["sw"][st["i"]]
                st[k].append((j, v))
                st["i"] += 1
        while zi < len(zones) and zones[zi].known <= t_close:
            active.append(zones[zi])
            zi += 1
        if i % 12 == 0:
            active = [z for z in active if z.dead > b.t and b.t - z.known <= age]
        rng = b.h - b.l
        A = adr[i]
        if rng <= 0 or A != A or i < win:
            continue
        tl_now = [(L["kind"], L["v1"] + L["slope"] * (b.t - L["t1"]) / TF["M30"]) for L in lines
                  if L["known"] <= t_close < L["dead"]]
        for side in ("SELL", "BUY"):
            sell = side == "SELL"
            kind = "S" if sell else "D"
            if sell:
                rej = (b.h - max(b.o, b.c)) / rng >= p.rej_wick and b.c < (b.h + b.l) / 2
            else:
                rej = (min(b.o, b.c) - b.l) / rng >= p.rej_wick and b.c > (b.h + b.l) / 2
            if not rej:
                continue
            seg = range(i - win, i + 1)
            head_i = max(seg, key=lambda x: m5[x].h) if sell else min(seg, key=lambda x: m5[x].l)
            head = m5[head_i].h if sell else m5[head_i].l
            ht = m5[head_i].t
            f = set()
            for z in active:
                if z.kind != kind or z.dead <= b.t or z.known > ht or not (z.lo - p.zone_tol <= head <= z.hi + p.zone_tol):
                    continue
                if z.tf in ("H1", "H4"):
                    f.add("z" + z.tf)
                    if z.first_touch >= m5[i - win].t - TF[z.tf]:
                        f.add("z" + z.tf + "f")
                if z.tf in ("M15", "H1") and getattr(z, "flip", False):
                    f.add("sbr")
            for tf in ("H1", "H4"):
                h, st = ind[tf], hsw[tf]
                kh = bisect.bisect_right(h["t"], ht) - 1
                src = st["H"] if sell else st["L"]
                kp = bisect.bisect_left(src, (kh, -1e18)) - 1
                if kp < 0 or src[kp][0] < kh - p.div_look[tf]:
                    continue
                j, v = src[kp]
                a_head, a_prev = _ao_at(h, m5, head_i, ht), h["ao"][j]
                if a_head == a_head and a_prev == a_prev and (
                        (sell and head > v and a_head < a_prev) or (not sell and head < v and a_head > a_prev)):
                    f.add("d" + tf)
            # trigger-at M5 (si ne bot/hierarchy.py)
            mids = los if sell else his
            k1 = bisect.bisect_left(mids, (head_i, -1e18)) - 1
            if k1 >= 0 and head_i < i:
                mj, mv = mids[k1]
                after = m5[head_i + 1:i + 1]
                if (sell and min(x.c for x in after) < mv) or (not sell and max(x.c for x in after) > mv):
                    f.add("bos")
                    sh = his if sell else los
                    k2 = bisect.bisect_left(sh, (mj, -1e18)) - 1
                    if k2 >= 0:
                        ls = sh[k2][1]
                        if (sell and ls < head and b.h >= ls - 1.0) or (not sell and ls > head and b.l <= ls + 1.0):
                            f.add("qm")
            sh = his if sell else los
            k3 = bisect.bisect_left(sh, (head_i, -1e18)) - 1
            if k3 >= 0 and head_i - sh[k3][0] <= 48 and ao[head_i] == ao[head_i]:
                j, v = sh[k3]
                if (sell and head > v and ao[head_i] < ao[j]) or (not sell and head < v and ao[head_i] > ao[j]):
                    f.add("ao")
            ext = b.h if sell else b.l
            for z in active:
                if z.kind != kind or z.dead <= b.t or not (z.lo - 0.5 <= ext <= z.hi + 0.5) or \
                        z.first_touch < b.t - TF[z.tf] + TF["M5"]:
                    continue
                if z.tf == "M5" and getattr(z, "flip", False):
                    f.add("flip")
                if z.tf in ("M15", "M30"):
                    f.add("ltf")
            if any(k == kind and abs(ext - v) <= 0.03 * A for k, v in tl_now):
                f.add("tl")
            if not f & set(CTX):
                continue
            sl = b.h + p.sl_buf if sell else b.l - p.sl_buf
            if abs(b.c - sl) > p.max_sl:
                continue
            opp = "D" if sell else "S"
            near = [(z.hi if sell else z.lo) for z in active if z.kind == opp and z.tf != "M5" and z.dead > b.t
                    and z.first_touch >= b.t - TF[z.tf] + TF["M5"]]
            near += [v for k, v in tl_now if k == opp]
            near = sorted((c for c in near if (sell and c < b.c) or (not sell and c > b.c)), key=lambda c: abs(c - b.c))
            o_seg = m5[max(0, head_i - org):head_i + 1]
            origin = (min(x.l for x in o_seg) + p.tp_buf) if sell else (max(x.h for x in o_seg) - p.tp_buf)
            out.append(dict(i=i, t=t_close, side=side, entry_c=b.c, sl=sl, risk=abs(b.c - sl), feats=frozenset(f),
                            htf="", tps=near, origin=origin))
    return out


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    p = P()
    C = candidates(m5, p, prepare(m5, p))
    print(len(C), "kandidate")

# Rezultati (M5 nga llogaria, 26 jan - 25 sht 2026); SL >= 3$, TP >= 2R, nje pozicion njeheresh.
# Shembulli i pronarit (24 shtator): me koke 3 ore dhe wick 0.4 kapet SELL 14:10 UTC @ 4270.33,
#   SL 4273.67, kontekst zH1f + sbr, trigger flip, TP origjina 4245.28 -> +7.5R (15:10 UTC).
# U provuan 1008 kombinime (koka 3/6/8 ore, wick 0.4/0.5 x 12 kontekste x 7 trigger x 3 TP):
#   zH1f + bos, TP origin: 6h +121.9R (DD 35.6), 8h +151.4R (DD 33.8); 3h vetem +6.5 deri +31.5R.
#   zH1f + bos + ao, TP near (= moduli live): 6h +62.8R, 8h +86.8R (DD 16.8).
#   sbr + ao, TP near: +22.6R deri +140.0R sipas parametrave, DD 24-96R (i paqendrueshem).
#   Kontekstet H4 (zH4f, dH4) dhe dH1: negative ose te paqendrueshme ne njeren periudhe.
#   Modeli i shembullit (zH1f + sbr + flip, TP origin): -25.7R deri +7.9R; sbr + flip: -31R deri -50R.
# Ne modulin live, TP origin ne vend te near jep me shume R vetem kur dritarja eshte 6h, por
# drawdown-i dyfishohet (34-39R) dhe portofoli s'permiresohet (+256.8R DD 37.1 kundrejt +269.2R
# DD 18.8), prandaj moduli live mbetet i pandryshuar.
