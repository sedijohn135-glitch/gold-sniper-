"""Moduli i hierarkise: logjika e pronarit, hap pas hapi.

1. MURI: nje zone H1 (supply per SELL, demand per BUY) prekur per here te pare. Tregu levizet nga
   bleresit dhe shitesit: nese cmimi s'e thyen dot murin (asnje mbyllje pertej tij), ai s'ka force.
2. KONFIRMIMET brenda 8 oreve pas prekjes se pare (secili tip numerohet nje here):
   bos   - M5 mbyllet nen swing low-in e fundit para majes (thyerje strukture / M5 demand i thyer)
   ao    - divergjence AO ne M5: maja me e larte se swing high-i para saj, AO me i ulet
   qm    - Quasimodo: left shoulder < koka, thyerje e low-it ne mes, cmimi kthehet te left shoulder
   flip  - rejection-i prek nje zone M5 te thyer qe u kthye (demand i thyer -> supply), fresh
   tl    - rejection-i prek nje trendline M30 (nga mbylljet)
   ltf   - rejection-i prek nje zone fresh M15/M30 te te njejtes ane
3. HYRJA: qiri M5 rejection, hyrje ne mbyllje, SL pertej wick-ut (min 3$), TP te niveli fresh
   perballe (zone M15/M30/H1/H4 ose trendline) >= 2R.

Live perdoren muri H1 + bos + ao (P.need). Ne 8 muaj (M5 nga llogaria, 26 jan - 25 sht 2026):
214 trade, +100.2R, DD 14.8R (shk-maj +36.9R, qer-sht +63.3R). Si konfirmim i vetem, qm dhe tl
dolen negative; muri H4 humbi (-9.5R). Fitimi vjen nga pak trade te medha (SL i vogel, TP larg).
"""
import bisect
from dataclasses import dataclass, replace

from .confluence import TF, trendlines
from .strategy import adr_series
from .zones import SRV, aggregate, find_zones, swings, with_flips


def ao_series(bars):
    """Awesome Oscillator: SMA5 - SMA34 e cmimit mesatar (h+l)/2."""
    med = [(b.h + b.l) / 2 for b in bars]
    out = [float("nan")] * len(bars)
    s5 = s34 = 0.0
    for i, m in enumerate(med):
        s5 += m
        s34 += m
        if i >= 5:
            s5 -= med[i - 5]
        if i >= 34:
            s34 -= med[i - 34]
        if i >= 33:
            out[i] = s5 / 5 - s34 / 34
    return out


FEATS = ("bos", "qm", "ao", "flip", "tl", "ltf")


@dataclass
class P:
    disp: float = 1.5
    htf: tuple = ("H1",)         # H4 si mur humbi ne backtest (-9.5R), prandaj vetem H1
    window_h: float = 8          # sa ore pas prekjes se pare te murit kerkohet hyrja
    zone_age_days: float = 10
    zone_tol: float = 0.5        # $ jashte murit qe lejohet koka
    swing_k: int = 2
    ao_look: int = 48            # qirinj M5 mbrapa per swing-un e divergjences
    qm_tol: float = 1.0          # $: sa afer left shoulder
    touch_tol: float = 0.5       # $: sa afer zones M5-M30 duhet te preke rejection-i
    tl_tol_adr: float = 0.03
    rej_wick: float = 0.5
    sl_buf: float = 0.5
    min_sl: float = 3.0          # SL minimal ne $ (me i vogel zgjerohet)
    max_sl: float = 20.0
    min_rr: float = 2.0          # TP (niveli fresh perballe) duhet te jete >= kaq R larg
    need: tuple = ("bos", "ao")  # konfirmimet e detyrueshme


USD_FIELDS = ("zone_tol", "qm_tol", "touch_tol", "sl_buf", "min_sl", "max_sl")


def scaled(p: P, k: float) -> P:
    """E njejta strategji per nje simbol tjeter: vlerat ne $ shumezohen me k (p.sh. BTC ~15 x ari)."""
    return replace(p, **{f: getattr(p, f) * k for f in USD_FIELDS})


def _fresh(z, t):
    return z.first_touch >= t - TF[z.tf] + TF["M5"]


def prepare(m5, p: P):
    series = {"M5": m5, "M15": aggregate(m5, 15), "M30": aggregate(m5, 30),
              "H1": aggregate(m5, 60), "H4": aggregate(m5, 240, SRV)}
    zones = []
    for tf in ("M5", "M15", "M30", "H1", "H4"):
        base = find_zones(series[tf], TF[tf], p.disp, tf=tf)
        allz = with_flips(base, series[tf], TF[tf])
        for k, z in enumerate(allz):
            z.flip = k >= len(base)
        zones += allz
    zones.sort(key=lambda z: z.known)
    times = [b.t for b in m5]
    age = p.zone_age_days * 86_400_000
    # testet e murit: qiri i pare M5 qe prek zonen H1/H4 pas krijimit
    tests = []
    for z in zones:
        if z.tf not in p.htf:
            continue
        i = bisect.bisect_left(times, z.known)
        while i < len(m5) and m5[i].t < z.dead and m5[i].t - z.known <= age:
            b = m5[i]
            if (z.kind == "S" and b.h >= z.lo) or (z.kind == "D" and b.l <= z.hi):
                tests.append((i, z))
                break
            i += 1
    tests.sort(key=lambda x: x[0])
    sw = swings(m5, p.swing_k)
    return dict(zones=zones, tests=tests, lines=trendlines(series["M30"]), adr=adr_series(m5, 10),
                ao=ao_series(m5), sw=sw)


def candidates(m5, p: P, ind, start=0):
    """Te gjitha rejection-et brenda nje testi muri, me konfirmimet e tyre (qirinjte nga `start`)."""
    zones, tests, lines, adr, ao, sw = (ind[k] for k in ("zones", "tests", "lines", "adr", "ao", "sw"))
    win = int(p.window_h * 12)
    age = p.zone_age_days * 86_400_000
    # swing-et sipas indeksit te konfirmimit
    his, los = [], []   # (indeksi, cmimi) te konfirmuara deri tani
    si = ti = zi = 0
    active_t, active_z = [], []
    out = []
    for i, b in enumerate(m5):
        t_close = b.t + TF["M5"]
        while si < len(sw) and sw[si][0] <= i:
            _, j, k, v = sw[si]
            (his if k == "H" else los).append((j, v))
            si += 1
        while ti < len(tests) and tests[ti][0] <= i:
            active_t.append(dict(i0=tests[ti][0], z=tests[ti][1]))
            ti += 1
        while zi < len(zones) and zones[zi].known <= t_close:
            active_z.append(zones[zi])
            zi += 1
        active_z = [z for z in active_z if z.dead > b.t and b.t - z.known <= age]
        active_t = [T for T in active_t if i - T["i0"] <= win and T["z"].dead > b.t]
        A = adr[i]
        rng = b.h - b.l
        if i < start or not active_t or rng <= 0 or A != A:
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
            best = None
            for T in active_t:
                z = T["z"]
                if z.kind != kind:
                    continue
                seg = m5[T["i0"]:i + 1]
                if sell:
                    hi = max(range(len(seg)), key=lambda x: seg[x].h)
                    head_i, head = T["i0"] + hi, seg[hi].h
                    if head > z.hi + p.zone_tol:
                        continue
                else:
                    lo = min(range(len(seg)), key=lambda x: seg[x].l)
                    head_i, head = T["i0"] + lo, seg[lo].l
                    if head < z.lo - p.zone_tol:
                        continue
                f = set()
                # bos + qm
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
                            if ((sell and ls < head and b.h >= ls - p.qm_tol) or
                                    (not sell and ls > head and b.l <= ls + p.qm_tol)):
                                f.add("qm")
                # ao: swing-u para kokes ne te njejten ane
                sh = his if sell else los
                k3 = bisect.bisect_left(sh, (head_i, -1e18)) - 1
                if k3 >= 0 and head_i - sh[k3][0] <= p.ao_look and ao[head_i] == ao[head_i]:
                    j, v = sh[k3]
                    if (sell and head > v and ao[head_i] < ao[j]) or (not sell and head < v and ao[head_i] > ao[j]):
                        f.add("ao")
                ext = b.h if sell else b.l
                for zz in active_z:
                    if zz.kind != kind or not (zz.lo - p.touch_tol <= ext <= zz.hi + p.touch_tol) or not _fresh(zz, b.t):
                        continue
                    if zz.tf == "M5" and getattr(zz, "flip", False):
                        f.add("flip")
                    if zz.tf in ("M15", "M30"):
                        f.add("ltf")
                if any(k == kind and abs(ext - v) <= p.tl_tol_adr * A for k, v in tl_now):
                    f.add("tl")
                if best is None or len(f) > len(best[0]):
                    best = (f, z, head)
            if best is None:
                continue
            f, z, head = best
            sl = b.h + p.sl_buf if sell else b.l - p.sl_buf
            risk = abs(b.c - sl)
            if max(risk, p.min_sl) > p.max_sl:
                continue
            opp = "D" if sell else "S"
            tps = [(zz.hi if sell else zz.lo) for zz in active_z
                   if zz.kind == opp and zz.tf != "M5" and _fresh(zz, b.t)]
            tps += [v for k, v in tl_now if k == opp]
            tps = [c for c in tps if (sell and c < b.c) or (not sell and c > b.c)]
            out.append(dict(i=i, t=t_close, side=side, entry_c=b.c, sl=sl, risk=risk, feats=frozenset(f),
                            htf=z.tf, tps=sorted(tps, key=lambda c: abs(c - b.c))))
    return out


def pick(c, p: P):
    """Filtri live/backtest per nje kandidat: (sl, tp, risk) ose None."""
    if c["htf"] not in p.htf or not set(p.need) <= c["feats"]:
        return None
    risk = max(c["risk"], p.min_sl)
    tp = next((x for x in c["tps"] if abs(x - c["entry_c"]) >= p.min_rr * risk), None)
    if tp is None:
        return None
    sl = c["entry_c"] - risk if c["side"] == "BUY" else c["entry_c"] + risk
    return sl, tp, risk


def signal(m5, p: P, ind=None):
    """Sinjali ne mbylljen e qirit te fundit M5: dict(side, sl, tp, risk, feats, htf) ose None."""
    ind = ind or prepare(m5, p)
    for c in candidates(m5, p, ind, start=len(m5) - 1):
        got = pick(c, p)
        if got:
            sl, tp, risk = got
            return dict(side=c["side"], sl=sl, tp=tp, risk=risk, feats=sorted(c["feats"]), htf=c["htf"])
    return None
