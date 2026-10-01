"""Trendline Breakout Trading Strategy (forextrendlinetrading.com), rregullat fjale per fjale, XAUUSD H1.

Trendline-t: vija rritese nga dy fundet e fundit swing H1 (L1 < L2, maja/fund i konfirmuar `k` qirinj me vone),
pa asnje mbyllje H1 nen vije mes tyre; vija zbritese nga dy majat e fundit (H1 > H2). Vija zgjatet djathtas.
SELL (BUY = pasqyra):
  #1 thyerja e menjehershme: qiri H1 MBYLLET nen vijen rritese (qiri para ishte mbi) -> sell stop pak nen low-in e tij
     (vlen `wait` qirinj H1), SL pak mbi high-in e tij.
  #2 pullback: pas thyerjes, brenda `pb_bars` qirinjve, qiri H1 qe prek/afrohet vijes se thyer (deri `pb_tol` x ATR)
     dhe mbyllet nen te -> sell stop nen low-in e tij, SL mbi high-in e tij.
  TP: "brenda fundit te meparshem te rendesishem" = fundi swing H1 me i ulet i `tp_look` qirinjve te fundit nen hyrje;
      nese s'ka (ose me pak se `min_rr` R), TP = `rr` R.
  Qiri i thyerjes shume i gjate (range > `max_rng` x ATR) -> s'hyhet ("long breakout candle = large SL").
  SL ne hyrje kur fitimi = rreziku (libri), mbyllje 22:30, hyrje 02:00-22:00, 1 pozicion, stop pas 2 humbjeve.
Ekzekutimi: qirinj M15 (stop-i mbushet kur cmimi e prek; SL para TP ne te njejtin qiri).

    python -m research.tlbo <hist_m5.pkl> <m5_2026.pkl> [variantet]
"""
import pickle
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.report import local
from bot.strategy import atr_series
from bot.zones import aggregate

H1 = 3_600_000
M15 = 900_000


def lt(t):
    return local(datetime.fromtimestamp(t / 1000, timezone.utc))


@dataclass
class P:
    k: int = 3
    setups: tuple = (1, 2)
    wait: int = 3
    pb_bars: int = 24
    pb_tol: float = 0.2
    max_rng: float = 2.0
    off: float = 0.3        # $ "pak pips" pertej qirit
    tp: str = "swing"       # swing / rr
    rr: float = 2.0
    min_rr: float = 1.0
    tp_look: int = 120
    min_sl: float = 3.0
    max_sl: float = 25.0
    start: int = 2
    maxloss: int = 2
    be: float = 1.0


def h1_signals(h1, p, k=1.0):
    """Urdhrat stop qe krijohen ne mbyllje te qirinjve H1: dict(t_from, t_to, side, stop, sl, tp_lvl)."""
    atr = atr_series(h1, 14)
    n = len(h1)
    hi_piv, lo_piv = [], []          # (indeksi, cmimi), te konfirmuar
    out, broken = [], []             # vijat e thyera ne pritje te pullback-ut
    for i in range(n):
        c = i - p.k                   # qiri qe konfirmohet tani si maje/fund
        if c >= p.k:
            w = h1[c - p.k:c + p.k + 1]
            if h1[c].h == max(x.h for x in w):
                hi_piv.append((c, h1[c].h))
            if h1[c].l == min(x.l for x in w):
                lo_piv.append((c, h1[c].l))
        a = atr[i]
        if a != a or i < 1:
            continue
        b, pb = h1[i], h1[i - 1]
        for up in (True, False):
            piv = lo_piv if up else hi_piv
            if len(piv) < 2:
                continue
            (i1, p1), (i2, p2) = piv[-2], piv[-1]
            if (up and p2 <= p1) or (not up and p2 >= p1):
                continue
            slope = (p2 - p1) / (i2 - i1)
            # asnje mbyllje pertej vijes mes dy pikave dhe pas pikes 2 deri te qiri para
            ok = all((h1[x].c >= p1 + slope * (x - i1)) if up else (h1[x].c <= p1 + slope * (x - i1))
                     for x in range(i1, i))
            if not ok:
                continue
            v, vp = p1 + slope * (i - i1), p1 + slope * (i - 1 - i1)
            if (up and b.c < v and pb.c >= vp) or (not up and b.c > v and pb.c <= vp):
                side = "SELL" if up else "BUY"
                broken.append(dict(i=i, side=side, i1=i1, p1=p1, slope=slope))
                if 1 in p.setups and (b.h - b.l) <= p.max_rng * a:
                    out.append(_order(h1, i, side, p, a, lo_piv if up else hi_piv, k))
        keep = []
        for br in broken:
            if i - br["i"] > p.pb_bars or i == br["i"]:
                if i == br["i"]:
                    keep.append(br)
                continue
            v = br["p1"] + br["slope"] * (i - br["i1"])
            sell = br["side"] == "SELL"
            if (sell and b.c > v) or (not sell and b.c < v):
                continue                                   # cmimi u kthye pertej vijes: thyerja deshtoi
            near = (b.h >= v - p.pb_tol * a) if sell else (b.l <= v + p.pb_tol * a)
            if near and 2 in p.setups and (b.h - b.l) <= p.max_rng * a:
                out.append(_order(h1, i, br["side"], p, a, lo_piv if sell else hi_piv, k))
                continue
            keep.append(br)
        broken = keep
    return [o for o in out if o]


def _order(h1, i, side, p, a, piv, k):
    b = h1[i]
    sell = side == "SELL"
    stop = b.l - p.off * k if sell else b.h + p.off * k
    sl = b.h + p.off * k if sell else b.l - p.off * k
    lv = [x for j, x in piv if i - j <= p.tp_look and ((sell and x < stop) or (not sell and x > stop))]
    tp_lvl = (max(lv) if sell else min(lv)) if lv else None     # fundi/maja me e afert (brenda fundit te meparshem)
    return dict(t_from=b.t + H1, t_to=b.t + H1 + p.wait * H1, side=side, stop=stop, sl=sl, tp_lvl=tp_lvl)


def run(m15, h1, k=1.0, spread=0.2, p=P()):
    orders = sorted(h1_signals(h1, p, k), key=lambda o: o["t_from"])
    T, pos, per_day, loss_day, oi, live = [], None, {}, {}, 0, []
    for b in m15:
        L = lt(b.t)
        while oi < len(orders) and orders[oi]["t_from"] <= b.t:
            live.append(orders[oi]); oi += 1
        if pos:
            sell = pos["side"] == "SELL"
            o, hi, lo = (b.o + spread, b.h + spread, b.l + spread) if sell else (b.o, b.h, b.l)
            x = None
            if L.weekday() >= 5 or (L.hour, L.minute) >= (22, 30):
                x = b.o + (spread if sell else 0)
            elif (sell and o >= pos["sl"]) or (not sell and o <= pos["sl"]):
                x = o
            elif (sell and hi >= pos["sl"]) or (not sell and lo <= pos["sl"]):
                x = pos["sl"]
            elif (sell and lo <= pos["tp"]) or (not sell and hi >= pos["tp"]):
                x = pos["tp"]
            else:
                fav = (pos["entry"] - lo) if sell else (hi - pos["entry"])
                if p.be and fav >= p.be * pos["risk"]:
                    pos["sl"] = min(pos["sl"], pos["entry"] - spread) if sell else max(pos["sl"], pos["entry"] + spread)
            if x is not None:
                pnl = (pos["entry"] - x) if sell else (x - pos["entry"])
                pos.update(usd=pnl / k, r=pnl / pos["risk"], exit_t=b.t)
                T.append(pos)
                if pnl < 0:
                    d = lt(pos["t"]).date(); loss_day[d] = loss_day.get(d, 0) + 1
                pos = None
        keep = []
        for o in live:
            if b.t >= o["t_to"]:
                continue
            sell = o["side"] == "SELL"
            hit = (b.l <= o["stop"]) if sell else (b.h + spread >= o["stop"])
            if not hit:
                keep.append(o); continue
            if pos is not None or L.weekday() >= 5 or not (p.start <= L.hour < 22) or per_day.get(L.date(), 0) >= 4 \
                    or (p.maxloss and loss_day.get(L.date(), 0) >= p.maxloss):
                continue
            entry = min(b.o, o["stop"]) if sell else max(b.o + spread, o["stop"])
            risk = max(abs(o["sl"] - entry), p.min_sl * k)
            if risk > p.max_sl * k:
                continue
            tp = None
            if p.tp == "swing" and o["tp_lvl"] is not None and abs(entry - o["tp_lvl"]) >= p.min_rr * risk:
                tp = o["tp_lvl"]
            if tp is None:
                tp = entry - p.rr * risk if sell else entry + p.rr * risk
            pos = dict(side=o["side"], entry=entry, risk=risk, t=b.t, sl=entry + risk if sell else entry - risk, tp=tp)
            per_day[L.date()] = per_day.get(L.date(), 0) + 1
        live = keep
    return T


def stats(T):
    eq = pk = dd = 0
    for x in sorted(T, key=lambda x: x["t"]):
        eq += x["usd"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    w = sum(x["r"] > 0.05 for x in T)
    return f"{len(T):5} tr {sum(x['usd'] for x in T):+7.0f}$ DD {dd:5.0f}$ fit {w / max(len(T), 1):4.0%}"


def evaluate(hist, m26, p):
    a = run(aggregate(m26, 15), aggregate(m26, 60), p=p)
    H = []
    for y in range(2016, 2026):
        t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        b5 = [b for b in hist if t0 - 40 * 86400000 <= b.t < t0 + 366 * 86400000]
        k = statistics.median(b.c for b in b5 if b.t >= t0) / 4513.71
        H += [x for x in run(aggregate(b5, 15), aggregate(b5, 60), k=k, spread=0.2 * k, p=p)
              if t0 <= x["t"] < t0 + 365.25 * 86400000]
    return a, H


if __name__ == "__main__":
    hist = pickle.load(open(sys.argv[1], "rb"))
    m26 = pickle.load(open(sys.argv[2], "rb"))
    V = eval(sys.argv[3]) if len(sys.argv) > 3 else {"libri": {}}
    for name, kw in V.items():
        a, H = evaluate(hist, m26, P(**kw))
        print(f"{name:34} | 2026 {stats(a)} | 10v {stats(H)}", flush=True)
