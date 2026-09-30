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
#
# TP fikse + mbyllje ditore 20:30 UTC (22:30 ora e Shqiperise), sniper, 2026 (spread 0.2$):
#   si me pare (trailing, pa mbyllje ditore) +149.3R DD 21.4 | trailing + mbyllje ditore +69.8R DD 24.2
#   TP 2R+BE -23.8R | 3R+BE +33.2R | 4R+BE +48.1R DD 23.6 | 5R+BE +47.8R | 6R+BE +43.8R | 8R+BE +54.2R
#   pa BE me keq ne cdo rast. Boti live (vendimi i pronarit, 30 sht): TP 4R + BE 1R + mbyllje 22:30.
#
# Sniper-i vetem, TP 8R + BE 1R, pa mbyllje ditore (30 shtator), 2026 | 10 vjet (spread 0.2$):
#   gjithcka (si tani) 437 tr +106.7R DD 18.7 | -232.7R
#   pa ditet e rotacionit +49.3R DD 22.7 | -78.0R ; vetem pullback trendi +45.0R DD 43.7 | -151.2R
#   vetem maje/fund +18.2R DD 35.7 | -422.9R ; trailing gjithcka +149.3R | -375.0R
#   Rotacioni jep gati gjysmen e fitimit te 2026: mbetet.
#
# Sniper-i vetem pas rregullimit (dite rotacioni: gjithmone TP 0.3 x ADR), 2026 | 10 vjet:
#   INTRADAY trend pa TP deri 22:30 + BE 1R: 525 tr +73.3R DD 24.6 | -234.9R  (RR=0, DAILY_CLOSE_LOCAL=22:30)
#   intraday pa BE +40.2R | intraday trailing +67.3R | intraday TP 8R +67.5R
#   SWING TP 8R + BE, vetem e premte: +125.3R DD 20.7 | -342.5R ; swing trailing +148.4R
#   Hyrjet nga 05 UTC (07:00 ora e Shqiperise) ne vend te 01 UTC: intraday +46.9R (nga +73.3R), swing TP 8R +82.0R
#   (nga +125.3R). Boti live: 07:00-22:00 (vendimi i pronarit, 30 sht).
#
# Ora e fillimit te hyrjeve (sniper vetem, BE 1R), ora e Shqiperise | intraday 2026 / 10 vjet | swing TP 8R 2026 / 10 vjet:
#   02:00 +94.6 / -215.1 | +130.5 / -275.4     03:00 +73.3 / -234.9 | +125.3 / -342.5
#   04:00 +88.3 / -153.9 | +129.8 / -279.6     05:00 +60.7 / -348.9 | +82.8 / -336.6
#   06:00 +68.2 / -442.2 | +111.0 / -458.1     07:00 +46.9 / -499.3 | +82.0 / -511.8
#   08:00 +37.0 / -454.0 | +76.3 / -543.9      09:00 +60.7 / -332.5 | +90.4 / -420.2
#   04:00 eshte me e mira ne te dy periudhat per intraday. Boti live: 04:00-22:00 (30 sht).
#
# Dalja "ne kthese" (1 tetor), sniper intraday, hyrje 04:00-22:00, mbyllje 22:30, 2026 | 10 vjet:
#   si tani (rotacion TP 0.3 ADR, trend deri 22:30)    +96.4R DD 17.5 | -210.7R
#   dalje ne sinjalin e kundert + hyrje ne anen tjeter  +41.1R | -389.4R ; pa TP +37.1R | -328.8R ; pa BE +25.6R
#   dalje vetem ne maje/fund te kundert, pa rihyrje     +69.9R | -466.1R ; pa TP +69.0R | -375.6R
#   rotacion TP 0.2 ADR +92.0R | -159.3R ; 0.4 ADR +84.0R | -185.0R
#   konfirmimi i refuzimit 1 qiri +70.6R | -174.1R ; 3 qirinj +81.0R | -135.2R ; 4 qirinj +76.0R | -116.2R
#   Asnje dalje "ne kthese" s'e kalon rregullin e tanishem: sinjali i kundert vjen pasi cmimi ka kthyer.
#
# Hyrja dhe filtrat e dites (1 tetor), fitimi ne $ per 1 ons (0.01 lot) ne cmimin e sotem, 2026 | 10 vjet (DD):
#   si tani                        +813$ DD 215 | +38$ DD 1304
#   STOP pas 2 humbjeve ne dite    +713$ DD 239 | +594$ DD 901   <- boti live: MAX_DAILY_LOSSES=2
#   stop pas 1 humbjeje +70$ | +722$ ; pas 3 humbjeve +758$ | +180$ ; 2 humbje + hyrje nga 02:00 +746$ | +827$ DD 580
#   limit 25/50/75% drejt ekstremit -12$/+537$/+348$ | -727$/-304$/+196$ (me keq)
#   vetem ditet me trend +453$ | +484$ ; vetem rotacion +245$ | -1533$ ; rotacion me drejtimin e djeshem -474$ | -490$
#
# Filtri me model (1 tetor): 9,233 trade te sniper-it (2016-2026) me 22 vecori ne hyrje (ora, tipi i dites,
# pozicioni ne range-in e dites, EMA 20/50/200, bishti, eficienca, ADR relativ...). Walk-forward: cdo vit testohet
# me model te trajnuar vetem ne vitet para tij. Logjistik / GBM, mban 50-80% te sinjaleve:
#   2020-2026 te gjitha trade-t +1837$ | modeli me i mire +663$ (logjistik 65%), te tjeret -337$ deri +283$.
#   Modeli s'e dallon hyrjen fituese: rezultati i nje sinjali eshte praktikisht i paparashikueshem nga keto te dhena.
# TP ku dita mbush X x ADR (kthesa e pritur), 2026 | 10 vjet: 0.8 +722$ | -243$ ; 1.0 +807$ | -593$ ; 1.2 +791$ | -633$
#   vetem trend 1.0 +915$ | -747$ ; 1.0 + stop 2 +698$ | +117$ ; 1.5 trend + stop 2 +720$ | +288$
#   Asnje s'e kalon "stop pas 2 humbjeve" (+713$ | +594$).
