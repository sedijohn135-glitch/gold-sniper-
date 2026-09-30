"""Simulimi i rregullave LIVE te sniper-it (1 tetor 2026), per te testuar ide te reja.

Rregullat live: hyrje 02:00-22:00 ora e Shqiperise (start=2), mbyllje 22:30, max 4 trade/dite, max 1 pozicion,
BE ne 1R, dite rotacioni TP = 0.3 x ADR, dite trendi pa TP deri 22:30, stop pas 2 humbjeve ne dite (maxloss=2).
Fitimi raportohet ne $ per 1 ons (= 0.01 lot); per vitet 2016-2025 vlerat ne $ shkallezohen me
k = cmimi mesatar i vitit / 4513.71 qe vitet te krahasohen me cmimin e sotem.

    python -m research.sim_live_rules
Me data/ (paketa per analize): 2026 (26 jan - 30 sht) 421 trade +722$ DD 320$ | 10 vjet 6916 trade +796$ DD 633$.
"""
import os, sys, pickle, statistics, dataclasses as D
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.config import Config
from bot.strategy import prepare, detect
from bot.zones import aggregate
from bot.strategy import Bar
from bot.report import local
def lt(t): return local(datetime.fromtimestamp(t / 1000, timezone.utc))

def sim(bars, k=1.0, spread=0.2, rot_tp=0.3, be=1.0, start=4, lim=0.0, lim_bars=4, prevdir=False,
        maxloss=0, rot_only=False, trend_only=False):
    base = Config.from_env(); p = base.strategy
    min_sl, max_sl = base.min_sl * k, base.max_sl * k
    ind = prepare(bars, p)
    # drejtimi i dites se kaluar (mbyllja vs hapja), sipas dites lokale
    dayoc, prev = {}, {}
    for b in bars:
        d = lt(b.t).date(); o, c = dayoc.get(d, (b.o, b.c)); dayoc[d] = (o, b.c)
    ds = sorted(dayoc)
    for a, b2 in zip(ds, ds[1:]): prev[b2] = 1 if dayoc[a][1] > dayoc[a][0] else -1
    T, pos, pend, per_day, loss_day, last_i = [], None, None, {}, {}, -99
    def close(b, px, why):
        nonlocal pos
        buy = pos["side"] == "BUY"
        x = px if buy else px + spread
        pnl = (x - pos["entry"]) if buy else (pos["entry"] - x)
        pos.update(exit_t=b.t, why=why, usd=pnl / k, r=pnl / pos["risk"]); T.append(pos)
        if pnl < 0: loss_day[lt(pos["t"]).date()] = loss_day.get(lt(pos["t"]).date(), 0) + 1
        pos = None
    for i in range(len(bars)):
        b = bars[i]; L = lt(b.t)
        eod = L.weekday() >= 5 or (L.hour, L.minute) >= (22, 30)
        if pend and not pos:   # limit ne pritje
            if eod or i > pend["exp"]: pend = None
            else:
                buy = pend["side"] == "BUY"
                if (buy and b.l <= pend["entry"] - spread) or (not buy and b.h + spread >= pend["entry"]):
                    pos = pend; pos["t"] = b.t; pend = None
                    per_day[L.date()] = per_day.get(L.date(), 0) + 1
        if pos:
            buy = pos["side"] == "BUY"
            lo, hi = (b.l, b.h) if buy else (b.l + spread, b.h + spread)
            if eod: close(b, b.o, "22:30")
            elif (buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"]): close(b, pos["sl"] - (0 if buy else spread), "SL")
            elif pos["tp"] is not None and ((buy and hi >= pos["tp"]) or (not buy and lo <= pos["tp"])): close(b, pos["tp"] - (0 if buy else spread), "TP")
            else:
                fav = (hi - pos["entry"]) if buy else (pos["entry"] - lo)
                if be > 0 and fav >= be * pos["risk"]:
                    pos["sl"] = max(pos["sl"], pos["entry"] + spread) if buy else min(pos["sl"], pos["entry"] - spread)
        if pos or pend or i + 1 >= len(bars): continue
        nb = bars[i + 1]; NL = lt(nb.t)
        if NL.weekday() >= 5 or not (start <= NL.hour < 22) or per_day.get(NL.date(), 0) >= 4 or i - last_i < 4: continue
        if maxloss and loss_day.get(NL.date(), 0) >= maxloss: continue
        sig = detect(bars, i, p, ind)
        if not sig: continue
        if rot_only and sig.day != "ROT": continue
        if trend_only and sig.day == "ROT": continue
        if prevdir and prev.get(NL.date()) and (1 if sig.side == "BUY" else -1) != prev[NL.date()] and sig.day in ("ROT", ""): continue
        buy = sig.side == "BUY"
        mkt = nb.o + spread if buy else nb.o
        px = mkt - lim * (mkt - sig.extreme) if buy else mkt + lim * (sig.extreme - mkt)
        sl0 = sig.stop_loss
        risk = max(abs(px - sl0), min_sl)
        if risk > max_sl: continue
        sl = px - risk if buy else px + risk
        tp = None
        if sig.day == "ROT" and rot_tp:
            d = rot_tp * ind["adr"][i]; tp = mkt + d if buy else mkt - d   # TP i njejte si me treg
        o = dict(side=sig.side, entry=px, sl=sl, tp=tp, risk=risk, t=nb.t, day=sig.day, kind=sig.kind)
        last_i = i
        if lim > 0: o["exp"] = i + lim_bars; pend = o
        else: pos = o; per_day[NL.date()] = per_day.get(NL.date(), 0) + 1
    return T

def stats(T):
    eq = pk = dd = 0
    for x in sorted(T, key=lambda x: x["t"]): eq += x["usd"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    return f"{len(T):4} tr {sum(x['usd'] for x in T):+8.0f}$ DD {dd:5.0f}$"


def load(fn):
    out = []
    for line in open(fn).readlines()[1:]:
        t, o, h, l, c = line.strip().split(",")
        out.append(Bar(int(t), float(o), float(h), float(l), float(c)))
    return out

if __name__ == "__main__":
    D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    kw = dict(start=2, maxloss=2)
    b26 = load(os.path.join(D, "xauusd_m15_2026_ctrader.csv"))
    print("2026   ", stats(sim(b26, **kw)))
    hist = load(os.path.join(D, "xauusd_m15_2016_2025_histdata.csv")); H = []
    for y in range(2016, 2026):
        t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        b = [x for x in hist if t0 - 40 * 86400000 <= x.t < t0 + 366 * 86400000]
        k = statistics.median(x.c for x in b if x.t >= t0) / 4513.71
        H += [x for x in sim(b, k=k, spread=0.2 * k, **kw) if t0 <= x["t"] < t0 + 365.25 * 86400000]
    print("10 vjet", stats(H))
