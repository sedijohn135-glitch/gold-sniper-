"""Kerkim: left shoulder i QM H1/H4 si nivel konfluence (njesoj si zonat dhe trendline).
Rezultati (ari, 8 muaj): 178 QM H1 + 36 QM H4. Konfluenca >=4 me QM si nivel: 66 trade +21.3R
(pa QM +23.3R); >=3: +13.4R (pa QM +19.8R). QM HTF + >=1/2/3 zona fresh + rejection: -7.3R / -1.8R / -0.4R.
Pra QM-ja HTF si nivel nuk shton fitim. Nuk u fut ne botin live."""
import pickle, sys, bisect
from datetime import datetime, timezone
sys.path.insert(0, "/home/user/gold-sniper-")
from bot import confluence as CF
from bot.confluence import TF, HTF, weekend_or_offhours
from bot.zones import SRV, aggregate, swings
S = sys.argv[1] if len(sys.argv) > 1 else "./"
m5 = pickle.load(open(S + "m5.pkl", "rb")); cut = pickle.load(open(S + "bars.pkl", "rb"))[0].t
SPREAD = 0.2
def qm_levels(bars, tf_ms, tf, look=60):
    """QM: LS -> mid -> koka (HH/LL) -> mbyllje pertej mid. Niveli = LS; aktiv deri te prekja e pare (+1 ore)
    ose derisa cmimi mbyllet pertej kokes."""
    sw = swings(bars, 2); H, L, out = [], [], []
    for c, i, k, v in sw:
        (H if k == "H" else L).append((i, v))
        for kind, heads, mids in (("S", H, L), ("D", L, H)):
            if (k == "H") != (kind == "S") or len(heads) < 2: continue
            (li, ls), (hi, hd) = heads[-2], heads[-1]
            if hi - li > look or not ((kind == "S" and hd > ls) or (kind == "D" and hd < ls)): continue
            mm = [w for j, w in mids if li < j < hi]
            if not mm: continue
            mid = min(mm) if kind == "S" else max(mm)
            for x in range(c, min(len(bars), hi + look)):     # thyerja e mid pas konfirmimit te kokes
                b = bars[x]
                if (kind == "S" and b.c > hd) or (kind == "D" and b.c < hd): break
                if (kind == "S" and b.c < mid) or (kind == "D" and b.c > mid):
                    known = b.t + tf_ms; touch = None
                    for y in range(x + 1, min(len(bars), x + look)):
                        by = bars[y]
                        if (kind == "S" and by.c > hd) or (kind == "D" and by.c < hd): break
                        if (kind == "S" and by.h >= ls) or (kind == "D" and by.l <= ls): touch = by.t; break
                    dead = (touch + tf_ms + 3_600_000) if touch else known + look * tf_ms
                    out.append(dict(kind=kind, lvl=ls, head=hd, known=known, dead=dead, tf=tf)); break
    return out
QM = qm_levels(aggregate(m5, 60), TF["H1"], "H1") + qm_levels(aggregate(m5, 240, SRV), TF["H4"], "H4")
QM.sort(key=lambda q: q["known"])
def evaluate(b, adr, active, lines, qms, p, mode):
    rng = b.h - b.l
    if rng <= 0 or adr != adr: return None
    t_close = b.t + TF["M5"]
    tl_now = [(L["kind"], L["v1"] + L["slope"] * (b.t - L["t1"]) / TF["M30"]) for L in lines if L["known"] <= t_close < L["dead"]]
    tol = p.tl_tol_adr * adr
    fresh = lambda z: z.first_touch >= b.t - TF[z.tf] + TF["M5"]
    for side in ("SELL", "BUY"):
        sell = side == "SELL"; kind = "S" if sell else "D"
        rej = ((b.h - max(b.o, b.c)) / rng >= p.rej_wick and b.c < (b.h + b.l) / 2) if sell else ((min(b.o, b.c) - b.l) / rng >= p.rej_wick and b.c > (b.h + b.l) / 2)
        if not rej: continue
        ext = b.h if sell else b.l
        tfs_hit = {z.tf for z in active if z.kind == kind and z.lo - p.touch_tol <= ext <= z.hi + p.touch_tol and fresh(z)}
        hit_tl = any(k == kind and abs(ext - v) <= tol for k, v in tl_now)
        qm_hit = {q["tf"] for q in qms if q["kind"] == kind and q["known"] <= t_close < q["dead"] and abs(ext - q["lvl"]) <= max(tol, 1.0)
                  and ((sell and b.h < q["head"]) or (not sell and b.l > q["head"]))}
        n = len(tfs_hit) + hit_tl + len(qm_hit)
        if mode == "qm_plus_zones":        # QM HTF + >= k zona fresh ne te njejtin nivel
            if not qm_hit or len(tfs_hit) < p.min_conf: continue
        else:                              # konfluenca: QM numerohet si nivel
            if n < p.min_conf or not ((tfs_hit | qm_hit) & set(HTF)): continue
        sl = b.h + p.sl_buf if sell else b.l - p.sl_buf
        risk = max(abs(b.c - sl), p.min_sl)
        if risk > p.max_sl: continue
        opp = "D" if sell else "S"
        cands = [(z.hi if sell else z.lo) for z in active if z.kind == opp and z.tf != "M5" and fresh(z)] + [v for k, v in tl_now if k == opp]
        cands = [c for c in cands if (sell and c <= b.c - p.min_rr * risk) or (not sell and c >= b.c + p.min_rr * risk)]
        if not cands: continue
        return dict(side=side, sl=sl, tp=max(cands) if sell else min(cands), qm=bool(qm_hit))
    return None
def run(p, mode, ind):
    zones, lines, adr = ind["zones"], ind["lines"], ind["adr"]; age = p.zone_age_days * 86_400_000
    T, pos, zi, qi, active, qact = [], None, 0, 0, [], []
    for i, b in enumerate(m5):
        t_close = b.t + 300_000
        if pos:
            buy = pos["side"] == "BUY"; lo, hi = (b.l, b.h) if buy else (b.l + SPREAD, b.h + SPREAD)
            x = pos["sl"] if ((buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"])) else pos["tp"] if ((buy and hi >= pos["tp"]) or (not buy and lo <= pos["tp"])) else None
            d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
            if x is None and ((d.weekday() == 4 and d.hour >= 19) or d.weekday() >= 5): x = b.o
            if x is not None:
                pos["r"] = ((x - pos["entry"]) if buy else (pos["entry"] - x)) / pos["risk"]; T.append(pos); pos = None
        while zi < len(zones) and zones[zi].known <= t_close: active.append(zones[zi]); zi += 1
        while qi < len(QM) and QM[qi]["known"] <= t_close: qact.append(QM[qi]); qi += 1
        if i % 12 == 0:
            active = [z for z in active if z.dead > b.t and b.t - z.known <= age]; qact = [q for q in qact if q["dead"] > b.t]
        if pos is not None or weekend_or_offhours(t_close, 1, 20, 19): continue
        sig = evaluate(b, adr[i], [z for z in active if z.dead > b.t], lines, qact, p, mode)
        if not sig: continue
        buy = sig["side"] == "BUY"; entry = b.c + (SPREAD if buy else 0); risk = max(abs(entry - sig["sl"]), p.min_sl)
        pos = dict(side=sig["side"], entry=entry, risk=risk, t=t_close, sl=entry - risk if buy else entry + risk, tp=sig["tp"], qm=sig["qm"])
    tot = sum(x["r"] for x in T); A = sum(x["r"] for x in T if x["t"] < cut); eq = pk = dd = 0
    for x in T: eq += x["r"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    q = [x["r"] for x in T if x["qm"]]
    return f"{len(T):4} trade {tot:+6.1f}R DD {dd:5.1f} | shk-maj {A:+6.1f} qer-sht {tot-A:+6.1f} | me QM: {len(q)} trade {sum(q):+.1f}R"
print("QM te gjetura: H1", sum(q["tf"] == "H1" for q in QM), "H4", sum(q["tf"] == "H4" for q in QM))
ind = CF.prepare(m5, CF.ConfParams())
for mc in (3, 4):
    print(f"konfluenca >={mc}, QM si nivel shtese:", run(CF.ConfParams(min_conf=mc), "count", ind))
for k in (1, 2, 3):
    print(f"QM H1/H4 + >={k} zona fresh ne te njejtin nivel + rejection:", run(CF.ConfParams(min_conf=k, min_rr=2.0), "qm_plus_zones", ind))
