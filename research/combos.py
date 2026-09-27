"""Kerkim i te gjitha kombinimeve te konfluencave te pronarit mbi hyrjet ne zona supply/demand.

Ngjarja baze: prekja e pare e nje zone fresh S/D (M15 ose H1, bot.zones.find_zones), hyrje
(a) limit ne kufirin e afert ose (b) rejection M5 (mbyllje jashte zones brenda 1 ore).
Cdo hyrje ka 12 kushte (po/jo):

  h1      zona eshte H1
  m15     zona eshte M15
  cont    zone vazhdimi RBR/DBD (cmimi erdhi ne baze ne drejtimin e zones)
  snr     SNR ne te majte: maje/fund swing i 10 diteve para bazes brenda zones
  htf     zona mbivendoset me nje zone fresh te se njejtes ane ne TF me te larte (M15->H1, H1->H4)
  trend   trade-i ne drejtimin e trendit H1 (mbyllja H1 mbi/nen EMA50)
  disc    discount/premium: blerje nen hapjen e dites, shitje mbi te
  sess    seanca Londer/New York (07-16 UTC)
  ao      divergjence AO ne M5 ne prekje
  sweep   qiri i prekjes kap likuiditetin (thyen minimumin/maksimumin e 12 qirinjve M5 para)
  strong  largimi nga zona >= 2.5 ATR (jo vetem 1.5)
  young   zona me e re se 24 ore

Per cdo kombinim (2^12 = 4096, nga 0 kushte deri te te gjitha bashke) llogaritet rezultati i
hyrjeve qe i plotesojne te gjitha kushtet e kombinimit. Protokolli kunder "gjetjes me fat":
  - kombinimet renditen VETEM ne DEV 2016-2020 (me >= 150 trade, kosto 0.40$),
  - me te mirat kontrollohen nje here ne VAL 2021-2025 dhe ne 2026 (cTrader, 8 muaj).
Kostot (spread + komision + rreshqitje ne 4,500$, shkallezuar me cmimin): 0.20 / 0.40 / 0.66 $.
Hyrjet trajtohen si te pavarura (pa kufirin nje pozicion njeheresh) per renditjen.

    python -m research.combos <hist_m5.pkl> <m5_2026.pkl>
"""
import bisect
import pickle
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

from bot.confluence import weekend_or_offhours
from bot.hierarchy import ao_series
from bot.strategy import atr_series
from bot.zones import aggregate, find_zones, swings
from research.hierarchy import outcome

FEATS = ["h1", "m15", "cont", "snr", "htf", "trend", "disc", "sess", "ao", "sweep", "strong", "young"]
COSTS = (0.2, 0.4, 0.66)
M5 = 300_000
REF = 4513.71


def ema(xs, n):
    out, e, a = [], None, 2 / (n + 1)
    for x in xs:
        e = x if e is None else e + a * (x - e)
        out.append(e)
    return out


def zone_feats(bars, tf_ms, htf_zones):
    """Zonat e nje TF me konfluencat qe dihen ne krijim."""
    atr = atr_series(bars, 14)
    times = [b.t for b in bars]
    sw = sorted((i, p) for _, i, _, p in swings(bars, 3))
    sw_i = [x[0] for x in sw]
    out = []
    for z in find_zones(bars, tf_ms):
        kn = bisect.bisect_left(times, z.known) - 1          # qiri i fundit i mbyllur kur zona njihet
        j = kn - 3                                           # qiri baze (find_zones: look=3)
        if j < 4:
            continue
        a = atr[j]
        if a != a:
            continue
        buy = z.kind == "D"
        into = bars[j].c - bars[j - 3].o                     # levizja qe solli cmimin ne baze
        cont = (into > 0.5 * a) if buy else (into < -0.5 * a)
        nxt = bars[j + 1:j + 4]
        dep = (max(x.h for x in nxt) - bars[j].h) if buy else (bars[j].l - min(x.l for x in nxt))
        # swing-et e formuara para levizjes qe solli bazen (jo vete baza)
        left = sw[bisect.bisect_left(sw_i, j - 10 * 86_400_000 // tf_ms):bisect.bisect_left(sw_i, j - 6)]
        snr = any(z.lo <= p <= z.hi for _, p in left)
        htf = any(h.kind == z.kind and h.known <= z.known < h.dead and h.lo <= z.hi and z.lo <= h.hi
                  for h in htf_zones)
        out.append(dict(z=z, a=a, cont=cont, snr=snr, htf=htf, strong=dep >= 2.5 * a))
    return out


def candidates(m5):
    m15, h1, h4 = aggregate(m5, 15), aggregate(m5, 60), aggregate(m5, 240)
    zh4 = find_zones(h4, 4 * 3_600_000)
    zh1 = find_zones(h1, 3_600_000)
    Z = [dict(f, h1=False) for f in zone_feats(m15, 900_000, zh1)] + \
        [dict(f, h1=True) for f in zone_feats(h1, 3_600_000, zh4)]
    times = [b.t for b in m5]
    h1t = [b.t for b in h1]
    h1e = ema([b.c for b in h1], 50)
    ao = ao_series(m5)
    day_open = {}
    for b in m5:
        day_open.setdefault(b.t // 86_400_000, b.o)
    C = []
    for f in Z:
        z, a = f["z"], f["a"]
        buy = z.kind == "D"
        k0 = bisect.bisect_left(times, z.known)
        touch = None
        for k in range(k0, min(k0 + 2880, len(m5))):
            b = m5[k]
            if touch is None:
                if not ((buy and b.l <= z.hi) or (not buy and b.h >= z.lo)):
                    continue
                touch, ext = k, (b.l if buy else b.h)
                hi_ = bisect.bisect_right(h1t, b.t - 3_600_000) - 1      # H1 i fundit i mbyllur
                trend = hi_ >= 50 and ((h1[hi_].c > h1e[hi_]) if buy else (h1[hi_].c < h1e[hi_]))
                # kapje likuiditeti: thyen ekstremin e 4 oreve te fundit dhe mbyll perseri brenda
                prev = m5[max(0, k - 48):k]
                sweep = bool(prev) and ((b.l < min(x.l for x in prev) < b.c) if buy else
                                        (b.h > max(x.h for x in prev) > b.c))
                past = m5[max(0, k - 48):k - 6]
                aod = False
                if past and ao[k] == ao[k]:
                    m = min(range(len(past)), key=lambda q: past[q].l) if buy else \
                        max(range(len(past)), key=lambda q: past[q].h)
                    pk = max(0, k - 48) + m
                    if ao[pk] == ao[pk]:
                        aod = (b.l < past[m].l and ao[k] > ao[pk]) if buy else (b.h > past[m].h and ao[k] < ao[pk])
                base = dict(f, side="BUY" if buy else "SELL", trend=trend, sweep=sweep, ao=aod,
                            young=b.t - z.known < 86_400_000)
                del base["z"]
                ent = z.hi if buy else z.lo
                C.append(dict(base, mode="limit", i=k, t=b.t, entry_c=ent,
                              sl=z.lo - 0.1 * a if buy else z.hi + 0.1 * a))
            ext = min(ext, b.l) if buy else max(ext, b.h)
            if (buy and b.c < z.lo) or (not buy and b.c > z.hi) or k > touch + 12:
                break
            if (buy and b.c > z.hi) or (not buy and b.c < z.lo):
                C.append(dict(base, mode="rej", i=k, t=b.t + M5, entry_c=b.c,
                              sl=ext - 0.1 * a if buy else ext + 0.1 * a))
                break
    for c in C:
        d = day_open.get(c["t"] // 86_400_000, c["entry_c"])
        c["disc"] = (c["entry_c"] < d) if c["side"] == "BUY" else (c["entry_c"] > d)
        h = datetime.fromtimestamp(c["t"] / 1000, timezone.utc).hour
        c["sess"] = 7 <= h < 16
        c["m15"] = not c["h1"]
    return C


def results(m5, C, k, t0, t1):
    """R e cdo hyrjeje per cdo (kosto, TP)."""
    out = []
    for c in C:
        if not (t0 <= c["t"] < t1) or weekend_or_offhours(c["t"], 1, 20, 19):
            continue
        risk = abs(c["entry_c"] - c["sl"])
        if risk > 3 * c["a"]:
            continue
        risk = max(risk, 3 * k)
        buy = c["side"] == "BUY"
        cc = dict(c, sl=c["entry_c"] - risk if buy else c["entry_c"] + risk)
        rs = {}
        for rr in (2, 3):
            tp = c["entry_c"] + rr * risk if buy else c["entry_c"] - rr * risk
            for cost in COSTS:
                r, j = outcome(m5, cc, tp, min_sl=3 * k, spread=cost * k)
                rs[(rr, cost)] = (r, m5[j].t if j < len(m5) else 2**62)
        sig = sum(1 << q for q, f in enumerate(FEATS) if c[f])
        out.append((c["mode"], sig, c["t"], rs))
    return out


def table(rows):
    """{(mode, rr, cost): [(t, signature, r, exit_t)]} sipas kohes."""
    T = defaultdict(list)
    for mode, sig, t, rs in rows:
        for key, (r, x) in rs.items():
            T[(mode,) + key].append((t, sig, r, x))
    for v in T.values():
        v.sort()
    return T


def combo(tab, mask):
    """Si boti live: nje pozicion njeheresh (hyrje e re vetem pasi mbyllet e meparshmja)."""
    n = s = w = 0
    free = 0
    for t, sig, r, x in tab:
        if sig & mask == mask and t >= free:
            n, s, w, free = n + 1, s + r, w + (r > 0.05), x
    return n, s, w


def name(mask):
    return "+".join(f for q, f in enumerate(FEATS) if mask >> q & 1) or "(asnje kusht)"


if __name__ == "__main__":
    hist = pickle.load(open(sys.argv[1], "rb"))
    rows = {"DEV": [], "VAL": []}
    for y in range(2016, 2026):
        t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        t1 = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        b5 = [b for b in hist if t0 - 40 * 86_400_000 <= b.t < t1 + 10 * 86_400_000]
        k = statistics.median(b.c for b in b5 if t0 <= b.t < t1) / REF
        R = results(b5, candidates(b5), k, t0, t1)
        rows["DEV" if y <= 2020 else "VAL"] += R
        print(y, "hyrje", len(R), flush=True)
    m26 = pickle.load(open(sys.argv[2], "rb"))
    rows["2026"] = results(m26, candidates(m26), 1.0, m26[0].t + 40 * 86_400_000, 2**62)
    pickle.dump(rows, open("/tmp/combos_rows.pkl", "wb"))
    tabs = {p: table(r) for p, r in rows.items()}
    for mode in ("limit", "rej"):
        for rr in (2, 3):
            key = (mode, rr, 0.4)
            dev = tabs["DEV"][key]
            ranked = []
            for mask in range(1 << len(FEATS)):
                n, s, w = combo(dev, mask)
                if n >= 150:
                    ranked.append((s / n, mask, n))
            ranked.sort(reverse=True)
            print(f"\n=== {mode} TP{rr}R | {len(ranked)} kombinime me >= 150 trade ne DEV | 10 me te mirat ne DEV (kosto 0.40):")
            for avg, mask, n in ranked[:10]:
                line = f"{name(mask):40}"
                for p in ("DEV", "VAL", "2026"):
                    for cost in COSTS:
                        nn, ss, ww = combo(tabs[p][(mode, rr, cost)], mask)
                        if cost == 0.4:
                            line += f" | {p} {nn:5} tr {ss / max(nn, 1):+.3f}R"
                        else:
                            line += f" {ss / max(nn, 1):+.3f}"
                print(line)
            # konfluencat nje nga nje (DEV / VAL, kosto 0.40)
            base_d = combo(dev, 0)
            base_v = combo(tabs["VAL"][key], 0)
            print(f"  pa kusht: DEV {base_d[0]} tr {base_d[1] / base_d[0]:+.3f}R | VAL {base_v[0]} tr {base_v[1] / base_v[0]:+.3f}R")
            for q, f in enumerate(FEATS):
                d = combo(dev, 1 << q)
                v = combo(tabs["VAL"][key], 1 << q)
                print(f"  vetem {f:7}: DEV {d[0]:5} tr {d[1] / max(d[0], 1):+.3f}R | VAL {v[0]:5} tr {v[1] / max(v[0], 1):+.3f}R")
