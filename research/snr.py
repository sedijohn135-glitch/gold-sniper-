"""Dy setup-e te pronarit, te testuara ne ar (M5 per hyrjen, H1 per nivelet):

A) SNR BREAKOUT + RETEST + REJECTION
   Niveli: maja/fundi swing H1 (k=3). Thyerja: mbyllje H1 pertej nivelit >= 0.1 ATR(H1).
   Pas thyerjes cmimi largohet >= 0.5 ATR, pastaj kthehet te niveli (brenda 48 oreve):
   qiri M5 qe e prek nivelin (tol 0.15 ATR) dhe mbyll ne anen e thyerjes me bisht >= 60%
   te qirit -> hyrje ne mbyllje. SL nen bishtin e retestit - 0.1 ATR. Mbyllje M5 pertej
   nivelit me 0.3 ATR ne anen e gabuar = thyerje e deshtuar (s'ka trade).

B) RBR DEMAND / DBD SUPPLY + SNR NE TE MAJTE
   Zona H1: kembe hyrese (trup >= 0.6 ATR) + baza 1-2 qirinj (range <= 0.6 ATR) + kembe dalese
   (trup >= 0.8 ATR, mbyll pertej bazes). RBR/DBD = vazhdim; per krahasim edhe DBR/RBD (kthim).
   "SNR ne te majte": nje maje/fund swing H1 i 10 diteve para bazes brenda zones (+-0.1 ATR).
   Hyrja ne prekjen e pare te zones (fresh): (1) limit ne kufirin e afert, SL pertej kufirit te
   larget - 0.1 ATR; (2) rejection M5: brenda 1 ore pas prekjes, mbyllje M5 jashte zones, SL nen
   bishtin me te ulet - 0.1 ATR.

TP: 2R ose 3R. Nje pozicion njeheresh per cdo variant, hyrje 01-20 UTC, e premte mbyllet 19:00 UTC.
Ekzekuto nga rrenja e repo-s:
    python -m research.snr <m5.pkl> [k]                       (8 muajt nga cTrader, k=1)
    python -m research.snr --ten <hist_m5.pkl>                (10 vjet, cdo vit me shkallen e vet)
"""
import bisect
import pickle
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

from bot.confluence import weekend_or_offhours
from bot.strategy import atr_series
from bot.zones import aggregate, find_zones, swings
from research.hierarchy import outcome

H1 = 3_600_000
M5 = 300_000


def prep(m5):
    h1 = aggregate(m5, 60)
    return h1, atr_series(h1, 14), swings(h1, 3), [b.t for b in m5]


def snr_breakout(m5, h1, atr, sw, times):
    out = []
    for ci, i, kind, lvl in sw:
        buy = kind == "H"                         # rezistence e thyer lart -> blerje ne retest
        known = h1[ci].t + H1
        brk = None
        for j in range(ci + 1, min(ci + 240, len(h1))):
            a = atr[j]
            if a != a:
                break
            c = h1[j].c
            if (buy and c > lvl + 0.1 * a) or (not buy and c < lvl - 0.1 * a):
                brk = j
                break
        if brk is None:
            continue
        a = atr[brk]
        k0 = bisect.bisect_left(times, h1[brk].t + H1)
        away = False
        for k in range(k0, min(k0 + 576, len(m5))):
            b = m5[k]
            if (buy and b.c < lvl - 0.3 * a) or (not buy and b.c > lvl + 0.3 * a):
                break                             # thyerje e deshtuar
            if not away:
                away = (b.h >= lvl + 0.5 * a) if buy else (b.l <= lvl - 0.5 * a)
                continue
            rng = b.h - b.l
            if rng <= 0:
                continue
            if buy and b.l <= lvl + 0.15 * a and b.c > lvl and (b.c - b.l) >= 0.6 * rng:
                out.append(dict(i=k, t=b.t + M5, side="BUY", entry_c=b.c, sl=b.l - 0.1 * a, a=a, kind="A"))
                break
            if not buy and b.h >= lvl - 0.15 * a and b.c < lvl and (b.h - b.c) >= 0.6 * rng:
                out.append(dict(i=k, t=b.t + M5, side="SELL", entry_c=b.c, sl=b.h + 0.1 * a, a=a, kind="A"))
                break
    return out


def base_zones(h1, atr, sw, tf_ms=H1, lin=0.6, lbase=0.7, lout=0.8):
    """Zonat baze (H1 ose M15): (tipi, D/S, lo, hi, koha kur njihet, snr ne te majte, atr).
    Kembe hyrese: qiri me trup >= 0.6 ATR ose 3 qirinj me levizje neto >= 1 ATR."""
    sw_by_i = sorted((i, p) for _, i, _, p in sw)
    sw_i = [x[0] for x in sw_by_i]
    out = []
    for j in range(15, len(h1) - 3):
        a = atr[j]
        if a != a:
            continue
        leg_in = h1[j - 1]
        din = leg_in.c - leg_in.o
        if abs(din) < lin * a:
            din = h1[j - 1].c - h1[j - 3].o
            if abs(din) < 1.0 * a:
                continue
        for n in (1, 2, 3):
            base = h1[j:j + n]
            if any(b.h - b.l > lbase * a for b in base) or j + n >= len(h1):
                continue
            lo, hi = min(b.l for b in base), max(b.h for b in base)
            out_b = h1[j + n]
            dout = out_b.c - out_b.o
            if dout >= lout * a and out_b.c > hi:
                kind, z = ("RBR" if din > 0 else "DBR"), "D"
                hi = max(max(b.o, b.c) for b in base)
            elif dout <= -lout * a and out_b.c < lo:
                kind, z = ("DBD" if din < 0 else "RBD"), "S"
                lo = min(min(b.o, b.c) for b in base)
            else:
                continue
            # SNR ne te majte: swing H1 i 10 diteve para bazes brenda zones
            left = sw_by_i[bisect.bisect_left(sw_i, j - 10 * 86_400_000 // tf_ms):bisect.bisect_left(sw_i, j - 1)]
            snr = any(lo - 0.1 * a <= p <= hi + 0.1 * a for _, p in left)
            out.append((kind, z, lo, hi, out_b.t + tf_ms, snr, a))
            break
    return out


def basic_zones(bars, atr, tf_ms):
    """Supply/demand bazike (bot.zones.find_zones: qiri baze para nje renieje >= 1.5 ATR)."""
    times = [b.t for b in bars]
    out = []
    for z in find_zones(bars, tf_ms):
        i = max(bisect.bisect_left(times, z.known) - 1, 0)
        a = atr[i]
        if a == a:
            out.append(("SD", z.kind, z.lo, z.hi, z.known, False, a))
    return out


def zone_entries(m5, times, zones):
    out = []
    for kind, z, lo, hi, known, snr, a in zones:
        buy = z == "D"
        k0 = bisect.bisect_left(times, known)
        touch = None
        for k in range(k0, min(k0 + 2880, len(m5))):        # 10 dite
            b = m5[k]
            if touch is None:
                if (buy and b.l <= hi) or (not buy and b.h >= lo):
                    touch = k
                    base = dict(kind=kind, snr=snr, side="BUY" if buy else "SELL", a=a)
                    # (1) limit ne kufirin e afert
                    out.append(dict(base, mode="limit", i=k, t=b.t, entry_c=hi if buy else lo,
                                    sl=lo - 0.1 * a if buy else hi + 0.1 * a))
                    ext = b.l if buy else b.h
                else:
                    continue
            ext = min(ext, b.l) if buy else max(ext, b.h)
            if (buy and b.c < lo) or (not buy and b.c > hi):
                break                                           # zona u thye
            if k > touch + 12:
                break
            if (buy and b.c > hi) or (not buy and b.c < lo):    # (2) rejection M5
                out.append(dict(base, mode="rej", i=k, t=b.t + M5, entry_c=b.c,
                                sl=ext - 0.1 * a if buy else ext + 0.1 * a))
                break
    return out


def trade(m5, cands, rr, spread, min_sl, t0=0):
    T, free = [], -1
    for c in sorted(cands, key=lambda c: c["i"]):
        if c["i"] <= free or c["t"] < t0 or weekend_or_offhours(c["t"], 1, 20, 19):
            continue
        risk = max(abs(c["entry_c"] - c["sl"]), min_sl)
        if risk > 3 * c["a"]:
            continue
        buy = c["side"] == "BUY"
        tp = c["entry_c"] + rr * risk if buy else c["entry_c"] - rr * risk
        cc = dict(c, sl=c["entry_c"] - risk if buy else c["entry_c"] + risk)
        b = m5[c["i"]]
        if c.get("mode") == "limit" and ((buy and b.l <= cc["sl"]) or (not buy and b.h + spread >= cc["sl"])):
            T.append(dict(t=c["t"], r=-1.0))      # limiti u mbush dhe SL u godit ne te njejtin qiri
            free = c["i"]
            continue
        r, j = outcome(m5, cc, tp, min_sl=min_sl, spread=spread)
        T.append(dict(t=c["t"], r=r))
        free = j
    return T


def stats(T):
    tot = sum(x["r"] for x in T)
    eq = peak = dd = 0.0
    for x in sorted(T, key=lambda x: x["t"]):
        eq += x["r"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    n = max(len(T), 1)
    return f"{len(T):5} trade {tot:+7.1f}R ({tot / n:+.3f}R/trade) fitime {sum(x['r'] > 0.05 for x in T) / n:4.0%} DD {dd:5.1f}R"


def variants(m5, k, spread, t0=0):
    h1, atr, sw, times = prep(m5)
    A = snr_breakout(m5, h1, atr, sw, times)
    Z = {}
    for tf, ms in (("H1", H1), ("M15", 15 * 60_000)):
        bars = h1 if tf == "H1" else aggregate(m5, 15)
        a = atr if tf == "H1" else atr_series(bars, 14)
        s = sw if tf == "H1" else swings(bars, 3)
        Z[tf] = zone_entries(m5, times, base_zones(bars, a, s, ms) + basic_zones(bars, a, ms))
    res = {}
    for rr in (2, 3):
        res[f"A snr break+retest+rej TP{rr}R"] = trade(m5, A, rr, spread, 3 * k, t0)
        for tf in Z:
            for mode in ("limit", "rej"):
                for grp, kinds in (("RBR/DBD", ("RBR", "DBD")), ("DBR/RBD", ("DBR", "RBD"))):
                    for snr in (True, None):
                        cs = [c for c in Z[tf] if c["mode"] == mode and c["kind"] in kinds and (snr is None or c["snr"])]
                        name = f"B {tf} {grp} {'+SNR majtas' if snr else 'te gjitha'} {mode} TP{rr}R"
                        res[name] = trade(m5, cs, rr, spread, 3 * k, t0)
                cs = [c for c in Z[tf] if c["mode"] == mode and c["kind"] == "SD"]
                res[f"C {tf} S/D bazike {mode} TP{rr}R"] = trade(m5, cs, rr, spread, 3 * k, t0)
    return res


if __name__ == "__main__":
    if sys.argv[1] == "--ten":
        m5 = pickle.load(open(sys.argv[2], "rb"))
        tot = defaultdict(list)
        for y in range(2016, 2026):
            t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            t1 = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            b5 = [b for b in m5 if t0 - 40 * 86_400_000 <= b.t < t1]
            k = statistics.median(b.c for b in b5 if b.t >= t0) / 4513.71
            for cost in (0.2, 0.66):
                for name, T in variants(b5, k, cost * k, t0).items():
                    tot[(name, cost)] += T
                    print(f"{y} kosto {cost:.2f} {name:48} {stats(T)}", flush=True)
        print("\n10 VJET (2016-2025):")
        for (name, cost), T in sorted(tot.items(), key=lambda x: (x[0][1], x[0][0])):
            print(f"kosto {cost:.2f} {name:48} {stats(T)}")
    else:
        m5 = pickle.load(open(sys.argv[1], "rb"))
        k = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
        for cost in (0.2, 0.66):
            for name, T in variants(m5, k, cost * k).items():
                print(f"kosto {cost:.2f} {name:48} {stats(T)}", flush=True)

# Rezultati 10 vjet (2016-2025, spread 0.20$ | kosto 0.66$), nje pozicion njeheresh:
#   A snr break+retest+rejection TP2R: 3914 trade -173.7R | -0.66: negativ. TP3R -150.5R.
#   B H1 RBR/DBD (me/pa SNR majtas): -32R deri +10R, afer zeros. DBR/RBD njesoj.
#   B M15 RBR/DBD rejection TP3R: +120.5R (0.090R/trade, 8/10 vite pozitive); +SNR majtas +111.5R, DD 26.6R.
#     Me kosto 0.66: -64.9R / -48.7R. Avantazhi eshte me i vogel se kostoja e plote.
#   C M15 S/D bazike limit TP3R: 11825 trade +65.2R (0.006R/trade = zero) | kosto 0.66: -1084.5R.
#     (Versioni i pare jepte +489.8R nga nje gabim: SL i goditur ne qirin e mbushjes s'numerohej.)
#     Ne 2026 (8 muaj, cTrader): +55.2R. Pa avantazh ne 10 vjet.
#   C H1 S/D bazike, rejection M15 bazike: negative.
