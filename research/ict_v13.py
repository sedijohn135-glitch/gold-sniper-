"""ICT Sniper V13 (specifika mekanike e pronarit, Modulet 1-6), XAUUSD M1.

Te dhenat: M1 2016-2025 (HistData, CSV ne UTC: time_utc,open,high,low,close) dhe M1 2026 nga cTrader (pickle Bar).
Ora e New York-ut (me DST). SELL (BUY = pasqyra):
  1. Dritaret NY: OR 01:30-02:00, 07:00-07:30, 13:30-14:00; SB 03-04, 10-11, 14-15; Macro 02:23-02:43, 03:53-04:13,
     07:50-08:10, 09:50-10:10, 10:50-11:10, 13:10-13:30; asnje hyrje 12:00-13:00. Mbushja e limitit duhet te jete
     brenda nje dritareje.
  2. Swing high = fractal 3-qirinjsh (H > H para dhe pas), i konfirmuar ne mbyllje te qirit pas. Ruhet maja e fundit
     e paprekur (BSL).
  3. Sweep: nje qiri e kalon BSL-ne me fitil. Brenda `react` qirinjve: displacement bearish = 1-3 qirinj bearish me
     trup total > `disp` x ATR(14) dhe fitila te vegjel (trup/range >= `body`), qe le FVG bearish (H3 < L1).
  4. Sell Limit te CE = (L1 + H3) / 2, i vlefshem `valid` qirinj; anulohet nese nje qiri mbyllet mbi L1 para mbushjes.
  5. SL = maja e sweep-it + 1$ (10 pips). Zero Float: mbyllje M1 mbi L1 (skaji i FVG) -> dalje ne mbyllje.
     TP1 = 2R (50%), TP2 = swing low-i me i afert nen hyrje (`tp`: "2r" / "swing" / "half" = 50/50).
  6. (opsione) `tstop`: 4 qirinj M1 rresht ne humbje pas hyrjes -> dalje; `shadow`: CE brenda fitilit te qirit te sweep-it.
Rregullat e botit: 1 pozicion, hyrje 02:00-22:00 ora e Shqiperise, 22:30, max `max_day` trade, stop pas 2 humbjeve.
Mbushja: SL kontrollohet ne qirin e mbushjes, TP vetem nga qiri tjeter (konservative).

    python -m research.ict_v13 <XAUUSD_M1_2016_2025.csv> <ct_XAUUSD_m1_2026.pkl> [variantet]
"""
import csv
import pickle
import statistics
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from research.qt_smt import lt, stats

NY = ZoneInfo("America/New_York")
WIN = {"london_or": (90, 120), "ny_or": (420, 450), "pm_or": (810, 840),
       "london_sb": (180, 240), "am_sb": (600, 660), "pm_sb": (840, 900),
       "m_lon_open": (143, 163), "m_lon_cont": (233, 253), "m_pre_ny": (470, 490),
       "m_ny_open": (590, 610), "m_lon_close": (650, 670), "m_pm_start": (790, 810)}
DEF = dict(disp=1.5, body=0.6, react=10, valid=30, buf=1.0, tp="2r", rr=2.0, zf=True, tstop=0, shadow=False,
           min_sl=1.0, max_sl=25.0, start=2, maxloss=2, max_day=4, wins=None)

_ny, _lt = {}, {}


def ny_min(t):
    """Minuta e dites ne NY (cache per ore)."""
    h = t // 3_600_000
    if h not in _ny:
        d = datetime.fromtimestamp(h * 3600, NY)
        _ny[h] = d.hour * 60
    return _ny[h] + (t // 60_000) % 60


def loc(t):
    h = t // 3_600_000
    if h not in _lt:
        _lt[h] = lt(h * 3_600_000)
    L = _lt[h]
    return L.weekday(), L.hour, (t // 60_000) % 60, L.date()


def window(m, p):
    if 720 <= m < 780:
        return None
    for name, (a, b) in WIN.items():
        if a <= m < b and (p["wins"] is None or name in p["wins"]):
            return name
    return None


def run(B, k=1.0, spread=0.2, p=None):
    """B = lista (t, o, h, l, c). Kthen trade-t me usd (0.01 lot, shkallezuar me k) dhe r."""
    p = dict(DEF, **(p or {}))
    n = len(B)
    tr = [0.0] * n
    for i in range(1, n):
        _, _, h, l, _ = B[i]; pc = B[i - 1][4]
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
    atr, s = [0.0] * n, 0.0
    for i in range(n):
        s += tr[i] - (tr[i - 14] if i >= 14 else 0)
        atr[i] = s / 14 if i >= 14 else 0
    T, pos, per_day, loss_day = [], None, {}, {}
    bsl = ssl = None                      # (indeksi, cmimi) maja/fundi i fundit i paprekur
    lows, highs = [], []                  # swing-et e konfirmuara per TP2
    sweeps = []                           # dict(side, s, ext) ne pritje te displacement
    orders = []                           # limit-et
    for i in range(2, n):
        t, o, h, l, c = B[i]
        wd, hr, mn, day = loc(t)
        # ---- pozicioni ----
        if pos:
            sell = pos["side"] == "SELL"
            o_, hi, lo, c_ = (o + spread, h + spread, l + spread, c + spread) if sell else (o, h, l, c)
            x = None
            if wd >= 5 or (hr, mn) >= (22, 30):
                x = o_
            elif (sell and o_ >= pos["sl"]) or (not sell and o_ <= pos["sl"]):
                x = o_
            elif (sell and hi >= pos["sl"]) or (not sell and lo <= pos["sl"]):
                x = pos["sl"]
            else:
                for leg in pos["legs"]:
                    if leg["x"] is None and ((sell and lo <= leg["tp"]) or (not sell and hi >= leg["tp"])):
                        leg["x"] = leg["tp"]
                if all(leg["x"] is not None for leg in pos["legs"]):
                    x = pos["legs"][-1]["x"]
                elif p["zf"] and ((sell and c > pos["edge"]) or (not sell and c < pos["edge"])):
                    x = c_
                elif p["tstop"]:
                    neg = (c_ > pos["entry"]) if sell else (c_ < pos["entry"])
                    pos["neg"] = pos["neg"] + 1 if neg else -10 ** 9      # vetem 4 qirinjte e pare pas hyrjes
                    if pos["neg"] >= p["tstop"]:
                        x = c_
            if x is not None:
                pnl = 0.0
                for leg in pos["legs"]:
                    lx = leg["x"] if leg["x"] is not None else x
                    pnl += leg["w"] * ((pos["entry"] - lx) if sell else (lx - pos["entry"]))
                pos.update(usd=pnl / k, r=pnl / pos["risk"], exit_t=t)
                T.append(pos)
                if pnl < 0:
                    loss_day[pos["day"]] = loss_day.get(pos["day"], 0) + 1
                pos = None
        # ---- limit-et ----
        m = ny_min(t)
        keep = []
        for od in orders:
            sell = od["side"] == "SELL"
            if i > od["exp"]:
                continue
            hit = (h + spread >= od["px"]) if sell else (l <= od["px"])
            if hit:
                w = window(m, p)
                if pos is None and w and wd < 5 and p["start"] <= hr < 22 and (hr, mn) < (22, 30) \
                        and per_day.get(day, 0) < p["max_day"] and not (p["maxloss"] and loss_day.get(day, 0) >= p["maxloss"]):
                    e = od["px"]
                    risk = abs(od["sl"] - e)
                    if p["min_sl"] * k <= risk <= p["max_sl"] * k:
                        lv = [x for _, x in (lows if sell else highs)[-50:] if (x < e - 0.5 * risk if sell else x > e + 0.5 * risk)]
                        sw = (max(lv) if sell else min(lv)) if lv else None
                        r2 = e - p["rr"] * risk if sell else e + p["rr"] * risk
                        if p["tp"] == "2r" or (p["tp"] == "swing" and sw is None):
                            legs = [dict(tp=r2, w=1.0)]
                        elif p["tp"] == "swing":
                            legs = [dict(tp=sw, w=1.0)]
                        else:
                            legs = [dict(tp=r2, w=0.5), dict(tp=sw if sw is not None else r2, w=0.5)]
                        for leg in legs:
                            leg["x"] = None
                        pos = dict(side=od["side"], entry=e, risk=risk, sl=od["sl"], edge=od["edge"], legs=legs,
                                   t=t, day=day, win=w, neg=0)
                        per_day[day] = per_day.get(day, 0) + 1
                        if (sell and h + spread >= pos["sl"]) or (not sell and l <= pos["sl"]):
                            pnl = -risk
                            pos.update(usd=pnl / k, r=-1.0, exit_t=t); T.append(pos)
                            loss_day[day] = loss_day.get(day, 0) + 1
                            pos = None
                continue                                        # i mbushur (ose i refuzuar) -> hiqet
            if (sell and c > od["edge"]) or (not sell and c < od["edge"]):
                continue                                        # FVG u invalidua para mbushjes
            keep.append(od)
        orders = keep
        # ---- sweep -> displacement + FVG (ne mbyllje te qirit i) ----
        a = atr[i]
        ks = []
        for sw in sweeps:
            sell = sw["side"] == "SELL"
            if i - sw["s"] > p["react"]:
                continue
            sw["ext"] = max(sw["ext"], h) if sell else min(sw["ext"], l)
            b1, b3 = B[i - 2], B[i]
            fvg = (b3[2] < b1[3]) if sell else (b3[3] > b1[2])
            ok = False
            if fvg and a > 0 and i - 2 >= sw["s"] - 1:
                for nn in (1, 2, 3):
                    seg = B[i - nn + 1:i + 1]
                    if i - nn + 1 < sw["s"]:
                        break
                    if not all((x[4] < x[1]) if sell else (x[4] > x[1]) for x in seg):
                        break
                    bod = sum(abs(x[4] - x[1]) for x in seg)
                    rng = sum(x[2] - x[3] for x in seg)
                    if bod > p["disp"] * a and bod >= p["body"] * rng:
                        ok = True; break
            if ok:
                edge = b1[3] if sell else b1[2]
                ce = (b1[3] + b3[2]) / 2 if sell else (b1[2] + b3[3]) / 2
                sb = B[sw["s"]]
                if p["shadow"] and not ((max(sb[1], sb[4]) <= ce <= sb[2]) if sell else (sb[3] <= ce <= min(sb[1], sb[4]))):
                    continue
                orders.append(dict(side=sw["side"], px=ce, edge=edge, exp=i + p["valid"],
                                   sl=sw["ext"] + p["buf"] * k if sell else sw["ext"] - p["buf"] * k))
                continue
            ks.append(sw)
        sweeps = ks
        # ---- sweep i ri i BSL/SSL ----
        if bsl and h > bsl[1]:
            sweeps.append(dict(side="SELL", s=i, ext=h)); bsl = None
        if ssl and l < ssl[1]:
            sweeps.append(dict(side="BUY", s=i, ext=l)); ssl = None
        # ---- swing i konfirmuar (qiri i-1) ----
        pb, cb, nb = B[i - 2], B[i - 1], B[i]
        if cb[2] > pb[2] and cb[2] > nb[2]:
            bsl = (i - 1, cb[2]); highs.append(bsl)
        if cb[3] < pb[3] and cb[3] < nb[3]:
            ssl = (i - 1, cb[3]); lows.append(ssl)
        # swing-et e kaluara per TP2 hiqen kur kalohen
        if lows and l < lows[-1][1]:
            lows = [x for x in lows if x[1] <= l]
        if highs and h > highs[-1][1]:
            highs = [x for x in highs if x[1] >= h]
    return T


def load_csv(path):
    out = []
    with open(path) as f:
        r = csv.reader(f); next(r)
        for row in r:
            t = int(datetime.strptime(row[0], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() * 1000)
            out.append((t, float(row[1]), float(row[2]), float(row[3]), float(row[4])))
    return out


def by_window(T):
    d = {}
    for x in T:
        d.setdefault(x["win"], []).append(x)
    return " ".join(f"{w}:{len(v)}/{sum(x['usd'] for x in v):+.0f}" for w, v in sorted(d.items()))


if __name__ == "__main__":
    H = load_csv(sys.argv[1])
    G26 = [(b.t, b.o, b.h, b.l, b.c) for b in pickle.load(open(sys.argv[2], "rb"))]
    V = eval(sys.argv[3]) if len(sys.argv) > 3 else {"V13": {}}
    years = {}
    for y in range(2016, 2026):
        t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        t1 = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        years[y] = [b for b in H if t0 - 86400000 <= b[0] < t1]
    years[2026] = G26
    for name, kw in V.items():
        R = {}
        for y, g in years.items():
            t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            k = 1.0 if y == 2026 else statistics.median(b[4] for b in g) / 4513.71
            R[y] = [x for x in run(g, k, 0.2 * k, kw) if x["t"] >= t0]
        A = [x for y, v in R.items() if y < 2026 for x in v]
        print(f"{name:26} | 2026 {stats(R[2026])} | 10v {stats(A)} | " +
              " ".join(f"{y % 100}:{sum(x['usd'] for x in v):+.0f}" for y, v in sorted(R.items())), flush=True)
        print(f"{'':26}   dritaret 10v: {by_window(A)}", flush=True)
