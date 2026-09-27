"""Kerkim: trendline (touch i 3-te) ne M15/M30/H1/H4 brenda modulit te konfluences.
Rezultati (ari, 8 muaj, >=4 nivele): M30 +23.3R (live), M15 +23.1R, H1 +20.1R, H4 +9.8R,
te gjitha TF bashke +10.9R. Me >=3 nivele: M30 +19.8R, H1 +24.8R, M15 +23.3R, te gjitha +5.0R.
Trendline-t ne me shume TF shtojne trade qe humbin; M30 mbetet."""
import pickle, sys
from datetime import datetime, timezone
sys.path.insert(0, "/home/user/gold-sniper-")
from bot import confluence as CF
from bot.confluence import TF, HTF, weekend_or_offhours
from bot.zones import SRV, aggregate
from research.brain import trendlines
S = sys.argv[1] if len(sys.argv) > 1 else "./"
m5 = pickle.load(open(S + "m5.pkl", "rb")); cut = pickle.load(open(S + "bars.pkl", "rb"))[0].t
SPREAD = 0.2
SER = {"M15": aggregate(m5, 15), "M30": aggregate(m5, 30), "H1": aggregate(m5, 60), "H4": aggregate(m5, 240, SRV)}
LINES = {tf: trendlines(SER[tf], TF[tf]) for tf in SER}
def evaluate(b, adr, active, lines, p, sep):
    rng = b.h - b.l
    if rng <= 0 or adr != adr: return None
    t_close = b.t + TF["M5"]; tol = p.tl_tol_adr * adr
    tl_now = [(L["kind"], L["v1"] + L["slope"] * (b.t - L["t1"]) / L["tf"], L["tf"]) for L in lines if L["known"] <= t_close < L["dead"]]
    fresh = lambda z: z.first_touch >= b.t - TF[z.tf] + TF["M5"]
    for side in ("SELL", "BUY"):
        sell = side == "SELL"; kind = "S" if sell else "D"
        rej = ((b.h - max(b.o, b.c)) / rng >= p.rej_wick and b.c < (b.h + b.l) / 2) if sell else ((min(b.o, b.c) - b.l) / rng >= p.rej_wick and b.c > (b.h + b.l) / 2)
        if not rej: continue
        ext = b.h if sell else b.l
        tfs_hit = {z.tf for z in active if z.kind == kind and z.lo - p.touch_tol <= ext <= z.hi + p.touch_tol and fresh(z)}
        tl_tfs = {tf for k, v, tf in tl_now if k == kind and abs(ext - v) <= tol}
        n = len(tfs_hit) + (len(tl_tfs) if sep else bool(tl_tfs))
        if n < p.min_conf or not tfs_hit & set(HTF): continue
        sl = b.h + p.sl_buf if sell else b.l - p.sl_buf; risk = max(abs(b.c - sl), p.min_sl)
        if risk > p.max_sl: continue
        opp = "D" if sell else "S"
        cands = [(z.hi if sell else z.lo) for z in active if z.kind == opp and z.tf != "M5" and fresh(z)] + [v for k, v, _ in tl_now if k == opp]
        cands = [c for c in cands if (sell and c <= b.c - p.min_rr * risk) or (not sell and c >= b.c + p.min_rr * risk)]
        if not cands: continue
        return dict(side=side, sl=sl, tp=max(cands) if sell else min(cands), tl=bool(tl_tfs))
    return None
def run(p, tfs, sep, ind):
    lines = sorted(sum((LINES[tf] for tf in tfs), []), key=lambda L: L["known"])
    zones, adr = ind["zones"], ind["adr"]; age = p.zone_age_days * 86_400_000
    T, pos, zi, li, active, act_l = [], None, 0, 0, [], []
    for i, b in enumerate(m5):
        t_close = b.t + 300_000
        if pos:
            buy = pos["side"] == "BUY"; lo, hi = (b.l, b.h) if buy else (b.l + SPREAD, b.h + SPREAD)
            x = pos["sl"] if ((buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"])) else pos["tp"] if ((buy and hi >= pos["tp"]) or (not buy and lo <= pos["tp"])) else None
            d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
            if x is None and ((d.weekday() == 4 and d.hour >= 19) or d.weekday() >= 5): x = b.o
            if x is not None: pos["r"] = ((x - pos["entry"]) if buy else (pos["entry"] - x)) / pos["risk"]; T.append(pos); pos = None
        while zi < len(zones) and zones[zi].known <= t_close: active.append(zones[zi]); zi += 1
        while li < len(lines) and lines[li]["known"] <= t_close: act_l.append(lines[li]); li += 1
        active = [z for z in active if z.dead > b.t and b.t - z.known <= age]
        if i % 12 == 0: act_l = [L for L in act_l if L["dead"] > b.t]
        if pos is not None or weekend_or_offhours(t_close, 1, 20, 19): continue
        sig = evaluate(b, adr[i], active, act_l, p, sep)
        if not sig: continue
        buy = sig["side"] == "BUY"; entry = b.c + (SPREAD if buy else 0); risk = max(abs(entry - sig["sl"]), p.min_sl)
        pos = dict(side=sig["side"], entry=entry, risk=risk, t=t_close, sl=entry - risk if buy else entry + risk, tp=sig["tp"], tl=sig["tl"])
    tot = sum(x["r"] for x in T); A = sum(x["r"] for x in T if x["t"] < cut); eq = pk = dd = 0
    for x in T: eq += x["r"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    q = [x["r"] for x in T if x["tl"]]
    return f"{len(T):4} trade {tot:+6.1f}R DD {dd:5.1f} | shk-maj {A:+6.1f} qer-sht {tot-A:+6.1f} | me TL: {len(q)} trade {sum(q):+.1f}R"
ind = CF.prepare(m5, CF.ConfParams())
for mc in (4, 3):
    p = CF.ConfParams(min_conf=mc)
    for tfs, sep, n in ((("M30",), False, "TL M30 (live)"), (("H1",), False, "TL H1"), (("H4",), False, "TL H4"), (("M15",), False, "TL M15"),
                        (("M15", "M30", "H1", "H4"), False, "TL ne cdo TF, numerohet 1 here"), (("M15", "M30", "H1", "H4"), True, "TL ne cdo TF, cdo TF nje nivel")):
        print(f">={mc} nivele | {n:32}", run(p, tfs, sep, ind))
