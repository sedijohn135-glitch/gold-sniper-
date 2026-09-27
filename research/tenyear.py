"""Backtest 10-vjecar (2016-2025) i moduleve te botit ne ar: sniper, hierarkia, konfluenca.

Te dhenat: HistData M1 XAUUSD (bid), pasqyra https://github.com/tiumbj/M1_XAUUSD. Ora e skedareve
eshte ora e New York-ut ME ore vere (hapja e se dieles 18:00 gjate gjithe vitit), prandaj
kthehet ne UTC me America/New_York.

Cmimi i arit ishte 1,100-3,500$ (sot ~4,500$): vlerat ne $ te strategjive (SL min/max,
tolerancat, spread-i) shkallezohen per cdo vit me k = cmimi mesatar i vitit / 4,513.71
(mesatarja e 8 muajve te testit origjinal), si per BTC-ne.

Ekzekuto nga rrenja e repo-s:
    python -m research.tenyear <dosja me DAT_MT_XAUUSD_M1_YYYY.csv> <cache.pkl>
"""
import contextlib
import dataclasses
import io
import os
import pickle
import statistics
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from backtest import run as sniper_run
from bot import confluence as CF, hierarchy as H
from bot.config import Config
from bot.confluence import weekend_or_offhours
from bot.strategy import Bar
from bot.zones import aggregate
import research.confluence as RC
from research.hierarchy import outcome

REF = 4513.71            # cmimi mesatar i 8 muajve (26 jan - 25 sht 2026)
NY = ZoneInfo("America/New_York")
YEARS = range(2016, 2026)
COSTS = {"spread 0.20$": 0.20, "kosto 0.66$": 0.66}   # ne 4,500$; 0.66 = modeli i ZIP-it (spread+komision+rreshqitje)


def load_m5(folder, years):
    """M1 (ora NY) -> M5 UTC."""
    out = {}
    for y in years:
        for line in open(os.path.join(folder, f"DAT_MT_XAUUSD_M1_{y}.csv")):
            d, hm, o, h, l, c, _ = line.strip().split(",")
            dt = datetime(int(d[:4]), int(d[5:7]), int(d[8:10]), int(hm[:2]), int(hm[3:5]), tzinfo=NY)
            t = int(dt.timestamp() * 1000)
            t5 = t - t % 300_000
            o, h, l, c = float(o), float(h), float(l), float(c)
            b = out.get(t5)
            out[t5] = Bar(t5, o, h, l, c) if b is None else Bar(t5, b.o, max(b.h, h), min(b.l, l), c)
    return [out[k] for k in sorted(out)]


def year_of(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).year


def sniper(b5, k, spread):
    base = Config.from_env()
    cfg = dataclasses.replace(base, min_sl=base.min_sl * k, max_sl=base.max_sl * k,
                              max_spread=base.max_spread * k, backtest_spread=spread)
    with contextlib.redirect_stdout(io.StringIO()):
        T, _ = sniper_run(aggregate(b5, 15), cfg, verbose=False)
    return [dict(t=x["t"], r=x["r"]) for x in T]


def hierarchy(b5, k, spread, cands=None):
    p = H.scaled(H.P(), k)
    cands = cands if cands is not None else H.candidates(b5, p, H.prepare(b5, p))
    T, free = [], -1
    for c in cands:
        if c["i"] <= free or weekend_or_offhours(c["t"], 1, 20, 19):
            continue
        g = H.pick(c, p)
        if not g:
            continue
        r, j = outcome(b5, c, g[1], min_sl=p.min_sl, spread=spread)
        T.append(dict(t=c["t"], r=r))
        free = j
    return T, cands


def confluence(b5, k, spread, ind=None):
    p = CF.scaled(CF.ConfParams(), k)
    ind = ind or CF.prepare(b5, p)
    RC.SPREAD = spread
    T, _ = RC.run(b5, p, ind)
    return [dict(t=x["t"], r=x["r"]) for x in T], ind


def stats(T):
    tot = sum(x["r"] for x in T)
    eq = peak = dd = 0.0
    for x in sorted(T, key=lambda x: x["t"]):
        eq += x["r"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    wins = sum(x["r"] > 0.05 for x in T)
    return f"{len(T):4} trade {tot:+7.1f}R ({tot / max(len(T), 1):+.3f}R/trade) fitime {wins / max(len(T), 1):4.0%} DD {dd:5.1f}R"


if __name__ == "__main__":
    folder, cache = sys.argv[1], sys.argv[2]
    if os.path.exists(cache):
        m5 = pickle.load(open(cache, "rb"))
    else:
        m5 = load_m5(folder, YEARS)
        pickle.dump(m5, open(cache, "wb"))
    print(len(m5), "qirinj M5", datetime.fromtimestamp(m5[0].t / 1000, timezone.utc), "-",
          datetime.fromtimestamp(m5[-1].t / 1000, timezone.utc), flush=True)
    mods = sys.argv[3].split(",") if len(sys.argv) > 3 else ["sniper", "hier", "conf"]
    allT = {(m, c): [] for m in mods for c in COSTS}
    for y in YEARS:
        # 40 dite para vitit per ADR/zonat; numerohen vetem trade-t e vitit
        start = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        b5 = [b for b in m5 if start - 40 * 86_400_000 <= b.t and year_of(b.t) <= y]
        k = statistics.median(b.c for b in b5 if b.t >= start) / REF
        cands = ind = None
        for cname, cost in COSTS.items():
            spread = cost * k
            for m in mods:
                if m == "sniper":
                    T = sniper(b5, k, spread)
                elif m == "hier":
                    T, cands = hierarchy(b5, k, spread, cands)
                else:
                    T, ind = confluence(b5, k, spread, ind)
                T = [x for x in T if year_of(x["t"]) == y]
                allT[(m, cname)] += T
                print(f"{y} k={k:.2f} {m:6} {cname:12} {stats(T)}", flush=True)
    print("\n10 VJET (2016-2025):")
    for (m, c), T in allT.items():
        print(f"{m:6} {c:12} {stats(T)}")
    for c in COSTS:
        T = [x for m in mods for x in allT[(m, c)]]
        print(f"TE GJITHA {c:12} {stats(T)}")

# Rezultati (HistData M1 2016-2025, cdo vit me shkallen e cmimit, spread 0.20$ / kosto 0.66$ ne 4,500$):
#   sniper      8559 trade -375.0R (-0.044R/trade) | kosto 0.66: -908.5R. Pozitiv vetem 2020, 2022, 2025.
#               Pa shkallezim te $ (k=1): -119.5R. I njejti kod ne 8 muajt e 2026: +149.3R (testi eshte i sakte).
#   hierarkia   3368 trade -144.1R (-0.043R/trade) | kosto 0.66: -551.0R. 2016 +67.6R, 2019 +37.7R, pjesa tjeter negative.
#   konfluenca  1304 trade   -6.0R (-0.005R/trade) | kosto 0.66: -179.3R.
#   Te gjitha   4672 trade -150.1R (hier+conf). Perfundimi: +296R i 8 muajve te 2026 s'perseritet ne 10 vjet;
#   2026 (ari 4,000-5,000$, levizje shume te medha) eshte nje periudhe e vecante per keto module.
