"""Setup-i "sniper advanced QM" i pronarit (shembulli 25 shtator 2026, 14:41 UTC):

  1. M30: bullish engulfing (qiri bullish qe mbyll mbi hapjen e qiririt bearish para tij).
  2. M1: supply-i me i afert thyhet paster. Zona "sniper" = hija e siperme e qiririt te fundit
     bullish te supply-t (nga mbyllja te maja).
  3. Cmimi kthehet ne zone dhe ben rejection -> BUY menjehere. SL 2$ (20 pips) nen zone.
  4. TP1-TP5: +2, +4, +6, +8, +10 $ nga hyrja. Per SELL: pasqyra.

Rregullat e testit (M1):
  - Supply: maje swing M1 (k=3) pas se ciles cmimi bie >= 2 ATR(M1) brenda 15 qirinjve; qiri i fundit
    bullish deri te maja jep zonen [mbyllja, maja], hija >= 0.05$.
  - Thyerje e paster: qiri qe mbyll mbi majen e swing-ut me trup >= 60% te qiririt (brenda 6 oreve).
  - Retest: brenda 30 qirinjve pas thyerjes, qiri qe prek zonen (low <= maja e zones) dhe mbyll
    >= fundi i zones -> hyrje ne mbyllje. Mbyllje nen SL-ne para kesaj anulon setup-in.
  - SL = fundi i zones - 2$, TP nga hyrja. Vlerat ne $ shkallezohen me cmimin e vitit (k).
  - M30: (a) pa filter; (b) engulfing i MBYLLUR ne 60 minutat para hyrjes (i tregtueshem);
    (c) hyrja brenda qiririt M30 qe PERFUNDON si engulfing (njohje e se ardhmes: s'mund te tregtohet,
    vetem per krahasim me shembullin).
  - Daljet: e gjitha ne TP1..TP5; shkalle 20% ne cdo TP (SL fiks); shkalle + SL ne hyrje pas TP1.
  - Hyrje 01-20 UTC, e premte mbyllet 19:00 UTC, nje pozicion njeheresh. Kosto 0.17$ (spread ~0.10$
    i pare ne cTrader + komision) dhe 0.30$, ne 4,500$.

    python -m research.qm_sniper <dosja HistData M1> <m1_2026.pkl> [close|arm|limit|stop]
"""
import os
import pickle
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bot.confluence import weekend_or_offhours
from bot.strategy import Bar, atr_series
from bot.zones import aggregate, swings

M1 = 60_000
M30 = 1_800_000
REF = 4513.71
NY = ZoneInfo("America/New_York")
TPS = (1, 2, 3, 4, 5)          # TP-te ne njesi 2$ (x k)
MODE = "close"   # "close": treg ne mbyllje te rejection-it | "arm": stop pas mbylljes nen zone, mbushje me vone
#                  "limit": limit ne zone pas thyerjes | "stop": stop i mbushur brenda te njejtit minut (OPTIMISTE: s'dihet renditja e cmimeve)
COSTS = (0.17, 0.30)
M30F = ("pa M30", "engulfing i mbyllur", "engulfing (e ardhmja)")


def load_year(folder, y):
    out = []
    for line in open(os.path.join(folder, f"DAT_MT_XAUUSD_M1_{y}.csv")):
        d, hm, o, h, l, c, _ = line.strip().split(",")
        dt = datetime(int(d[:4]), int(d[5:7]), int(d[8:10]), int(hm[:2]), int(hm[3:5]), tzinfo=NY)
        out.append(Bar(int(dt.timestamp() * 1000), float(o), float(h), float(l), float(c)))
    out.sort(key=lambda b: b.t)
    return out


def engulf_flags(m1):
    """{fillimi i qiririt M30: +1 bullish engulfing, -1 bearish engulfing}."""
    b30 = aggregate(m1, 30)
    out = {}
    for p, b in zip(b30, b30[1:]):
        if p.c < p.o and b.c > b.o and b.c > p.o and b.o <= p.c:
            out[b.t] = 1
        elif p.c > p.o and b.c < b.o and b.c < p.o and b.o >= p.c:
            out[b.t] = -1
    return out


def setups(m1, k, cost):
    """Hyrjet (buy stop ne fundin e zones pasi cmimi zbret nen te; shitja: pasqyra)."""
    atr = atr_series(m1, 14)
    sw = swings(m1, 3)
    n = len(m1)
    sp = cost * k
    out = []
    for ci, s, kind, px in sw:
        a = atr[s]
        if a != a or a <= 0:
            continue
        buy = kind == "H"            # supply i thyer -> blerje (demand i thyer -> shitje)
        # qiri i fundit bullish (bearish per demand) deri te maja: zona = hija e tij
        i = next((j for j in range(s, max(s - 6, -1), -1) if (m1[j].c > m1[j].o) == buy and m1[j].c != m1[j].o), None)
        if i is None:
            continue
        zb, zt = (m1[i].c, m1[i].h) if buy else (m1[i].c, m1[i].l)      # zb = kufiri i hyrjes
        if abs(zt - zb) < 0.05 * k:
            continue
        # thyerja: mbyllja e pare pertej majes pas swing-ut; me pare cmimi duhet te kete rene >= 2 ATR
        brk, ext = None, px
        for j in range(ci + 1, min(ci + 360, n)):
            b = m1[j]
            if (buy and b.c > px) or (not buy and b.c < px):
                rng = b.h - b.l
                clean = rng > 0 and abs(b.c - b.o) >= 0.6 * rng and (b.c > b.o) == buy
                if clean and ((buy and ext <= px - 2 * a) or (not buy and ext >= px + 2 * a)):
                    brk = j
                break
            ext = min(ext, b.l) if buy else max(ext, b.h)
        if brk is None:
            continue
        slp = zb - 2.0 * k if buy else zb + 2.0 * k
        if MODE == "limit":
            # limit ne kufirin e zones, i vendosur pas mbylljes se qiririt te thyerjes
            for j in range(brk + 1, min(brk + 31, n)):
                b = m1[j]
                if (buy and b.l + sp <= zb) or (not buy and b.h >= zb):
                    fill = min(zb, b.o + sp) if buy else max(zb, b.o)
                    out.append(dict(i=j, t=b.t + M1, side="BUY" if buy else "SELL", fill=fill, sl=slp, same=True))
                    break
            continue
        armed = False
        for j in range(brk + 1, min(brk + 31, n)):
            b = m1[j]
            if (buy and b.c <= slp) or (not buy and b.c >= slp):
                break                                            # zona u thye: anulohet
            if not armed:
                dip = (b.l < zb) if buy else (b.h > zb)          # cmimi kaloi fundin e zones
                if dip and ((buy and b.c >= zb) or (not buy and b.c <= zb)):
                    # u kthye ne te njejtin minut: MODE "stop" = stop-i mbushur ne zb brenda qiririt
                    # (optimiste: s'dihet renditja); MODE "close" = hyrje me treg ne mbyllje (e sigurt)
                    if MODE == "stop":
                        out.append(dict(i=j, t=b.t + M1, side="BUY" if buy else "SELL", fill=zb, sl=slp))
                    elif MODE == "arm":
                        pass                                     # s'dihet brenda qiririt: pa hyrje
                    else:
                        out.append(dict(i=j, t=b.t + M1, side="BUY" if buy else "SELL",
                                        fill=b.c + sp if buy else b.c, sl=slp))
                    break
                armed = dip and ((buy and b.c < zb) or (not buy and b.c > zb))   # mbylli pertej: stop-i vendoset
                continue
            if (buy and b.h + sp >= zb) or (not buy and b.l <= zb):
                fill = max(zb, b.o + sp) if buy else min(zb, b.o)
                out.append(dict(i=j, t=b.t + M1, side="BUY" if buy else "SELL", fill=fill, sl=slp,
                                same=True))
                break
    return sorted(out, key=lambda x: x["i"])


def simulate(m1, c, k, cost):
    """R per cdo menyre daljeje. Te dhenat jane bid: blerja hyn ne ask, shitja del ne ask."""
    buy = c["side"] == "BUY"
    sp = cost * k
    entry = c["fill"]
    risk = (entry - c["sl"]) if buy else (c["sl"] - entry)
    tps = [entry + (2.0 * k * q if buy else -2.0 * k * q) for q in TPS]
    hit = [None] * len(TPS)
    sl_i = sl_be = None
    close = None
    j = c["i"]
    # qiri i mbushjes (kur stop-i mbushet brenda tij): SL i goditur pas mbushjes s'mund te perjashtohet
    if c.get("same"):
        b = m1[c["i"]]
        if (buy and b.l <= c["sl"]) or (not buy and b.h + sp >= c["sl"]):     # konservative: humbje
            return {**{f"TP{q + 1}": -1.0 for q in range(len(TPS))}, "shkalle": -1.0, "shkalle+BE": -1.0}, b.t
    for j in range(c["i"] + 1, len(m1)):
        b = m1[j]
        lo, hi = (b.l, b.h) if buy else (b.l + sp, b.h + sp)      # cmimi me te cilin del pozicioni
        d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
        if (d.weekday() == 4 and d.hour >= 19) or d.weekday() >= 5 or j > c["i"] + 1440:
            close = b.o + (0 if buy else sp)
            break
        if hit[0] is not None and sl_be is None and ((buy and lo <= entry) or (not buy and hi >= entry)):
            sl_be = j
        if (buy and lo <= c["sl"]) or (not buy and hi >= c["sl"]):
            sl_i = j
            break
        for q, tp in enumerate(tps):
            if hit[q] is None and ((buy and hi >= tp) or (not buy and lo <= tp)):
                hit[q] = j
        if hit[-1] is not None:
            break

    def r_at(px):
        return ((px - entry) if buy else (entry - px)) / risk

    rest = -1.0 if sl_i is not None else (r_at(close) if close is not None else 0.0)
    part = [r_at(tps[q]) if hit[q] is not None else rest for q in range(len(TPS))]
    res = {f"TP{q + 1}": part[q] for q in range(len(TPS))}
    res["shkalle"] = sum(part) / len(TPS)
    be = []
    for q in range(len(TPS)):
        if hit[q] is not None and (sl_be is None or hit[q] < sl_be):
            be.append(r_at(tps[q]))
        elif hit[0] is not None and sl_be is not None:
            be.append(0.0)                                   # SL ne hyrje pas TP1
        else:
            be.append(rest)
    res["shkalle+BE"] = sum(be) / len(TPS)
    return res, m1[j].t


def run_period(m1, k, t0, t1, eng, cost):
    rows = []
    for c in setups(m1, k, cost):
        if not (t0 <= c["t"] < t1) or weekend_or_offhours(c["t"], 1, 20, 19):
            continue
        want = 1 if c["side"] == "BUY" else -1
        cur = c["t"] - M1 - (c["t"] - M1) % M30            # qiri M30 ku ndodh hyrja
        closed = any(eng.get(cur - q * M30) == want for q in (1, 2))    # engulfing i mbyllur <= 60 min
        future = eng.get(cur) == want                        # qiri aktual perfundon si engulfing
        rows.append((c["t"], closed, future, {cost: simulate(m1, c, k, cost)}))
    return rows


def stats(rows, flt, cost, exitk):
    n = s = w = 0
    free = 0
    for t, closed, future, out in rows:
        if flt == 1 and not closed or flt == 2 and not future or t < free:
            continue
        res, x = out[cost]
        r = res[exitk]
        n, s, w, free = n + 1, s + r, w + (r > 0.05), x
    return n, s, w


if __name__ == "__main__":
    folder, p26 = sys.argv[1], sys.argv[2]
    MODE = sys.argv[3] if len(sys.argv) > 3 else MODE
    per = {}
    for y in range(2016, 2026):
        t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        t1 = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        m1 = load_year(folder, y)
        k = statistics.median(b.c for b in m1) / REF
        eng = engulf_flags(m1)
        per[y] = {cost: run_period(m1, k, t0, t1, eng, cost) for cost in COSTS}
        print(y, "setup", len(per[y]), flush=True)
    m26 = pickle.load(open(p26, "rb"))
    eng = engulf_flags(m26)
    per[2026] = {cost: run_period(m26, 1.0, 0, 2**62, eng, cost) for cost in COSTS}
    print(2026, "setup", len(per[2026]), flush=True)
    exits = [f"TP{q}" for q in TPS] + ["shkalle", "shkalle+BE"]
    for cost in COSTS:
        for f, fname in enumerate(M30F):
            print(f"\n=== kosto {cost}$ | {fname}")
            for ex in exits:
                line = f"{ex:11}"
                for lbl, ys in (("2016-20", range(2016, 2021)), ("2021-25", range(2021, 2026)), ("2026", (2026,))):
                    N = S = W = 0
                    for y in ys:
                        n, s, w = stats(per[y][cost], f, cost, ex)
                        N, S, W = N + n, S + s, W + w
                    line += f" | {lbl}: {N:5} tr {S:+7.1f}R ({S / max(N, 1):+.3f}) fit {W / max(N, 1):4.0%}"
                print(line, flush=True)

# Rezultati (M1: HistData 2016-2025 + cTrader 26 jan - 25 sht 2026; kosto 0.17$; nje pozicion njeheresh).
# Shembulli i 25 shtatorit gjendet saktë: stop 4269.57, SL 4267.57, TP5 (+5R).
# R per trade, TP5 | shkalle 20%:
#   MODE           M30 filter              2016-20            2021-25            2026
#   stop (optim.)  pa filter               +0.172 | +0.146    +0.160 | +0.142    +0.362 | +0.280
#   stop (optim.)  engulfing (e ardhmja)   +0.725 | +0.628    +0.828 | +0.671    +1.052 | +0.778
#   close          engulfing i mbyllur     -0.095 | -0.106    -0.125 | -0.110    -0.087 | -0.061
#   arm            engulfing i mbyllur     -0.106 | -0.106    -0.121 | -0.100    +0.001 | -0.002
#   limit          engulfing i mbyllur     -0.187 | -0.196    -0.194 | -0.188    -0.232 | -0.217
#   close/arm/limit pa filter: te gjitha negative (-0.05 deri -0.20).
# Perfundimi: fitimi del vetem (1) kur stop-i supozohet i mbushur brenda te njejtit minut sa me mire
# (renditja e cmimeve brenda minutes s'dihet nga qirinjte M1; kur mbushja do te dilte keq, modeli e shtyn)
# dhe (2) kur engulfing-u M30 merret nga e ardhmja: ne shembull hyrja (14:41) eshte BRENDA qiririt M30
# (14:30-15:00) qe u be engulfing vetem ne 15:00. Menyrat qe nje bot mund t'i ekzekutoje (hyrje ne
# mbyllje, stop pas mbylljes, limit) jane negative ne 10 vjet dhe ~0 ne 2026. Me SL 2$ ne M1, spread-i
# (0.10$ + komision) eshte ~9% e rrezikut per cdo trade.
