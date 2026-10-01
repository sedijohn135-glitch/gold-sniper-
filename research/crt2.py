"""CRT Konservative H4 -> M5 (dokumenti i pronarit "Strategjia CRT ... Rregullat e Plota", 1 tetor 2026), XAUUSD.

Te dhenat: M5 nga cTrader (research/qt_smt.py i shkarkon). Ora e New York-ut (me DST).
  H4 i ankoruar ne 17:00 NY: 17, 21, 01, 05, 09, 13. C1 = qiri H4 kyc (hapja 01/05/09 NY; `keys`).
  Inside bar (H<=CRH dhe L>=CRL) -> C1 mbetet, pritet qiri tjeter (max `max_inside`).
  C2 SELL: High > CRH, CRL < Close < CRH, Low >= CRL (pa double purge), Close > EQ (TP1 s'eshte konsumuar).
  Purge-i (qiri i pare M5 qe kalon CRH) brenda 03:00-05:00 ose 08:00-10:00 NY (`win_only`).
  CISD bearish ne M5 brenda C2 pas purge-it: seria e fundit e qirinjve up-close drejt majes; open-i i te parit = niveli;
    nje trup M5 mbyllet nen te. OB open = ai nivel -> Sell Limit pas mbylljes se C2, i vlefshem deri ne fund te C3.
  Anulim: EQ preket para mbushjes, ose RR(hyrje -> CRL) < `min_rr`.
  SL = maja e sweep-it + buffer; TP1 = EQ (SL ne hyrje; me 0.01 lot s'ka mbyllje te pjesshme), TP2 = CRL.
  `tp1_close`=True: mbyll gjithcka te EQ (alternative). BUY = pasqyra.
Rregullat e botit: hyrje 02:00-22:00 ora e Shqiperise, 22:30, 1 pozicion, max 2 trade/dite, stop pas 2 humbjeve.

    python -m research.crt2 <ct_XAUUSD_m5.pkl> [variantet]
"""
import pickle
import statistics
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from research.qt_smt import lt, stats

NY = ZoneInfo("America/New_York")


def ny(t):
    return datetime.fromtimestamp(t / 1000, NY)


def h4_ny(m5):
    """Qirinjte H4 te ankoruar ne 17:00 NY. Kthen liste dict(t0, t1, o,h,l,c, open_h, bars=[indekset M5])."""
    out, cur, key = [], None, None
    for i, b in enumerate(m5):
        d = ny(b.t)
        hrs = (d.hour - 17) % 24
        k = ((d - __import__("datetime").timedelta(hours=17)).date(), hrs // 4)
        if k != key:
            if cur:
                out.append(cur)
            key = k
            cur = dict(o=b.o, h=b.h, l=b.l, c=b.c, open_h=(17 + (hrs // 4) * 4) % 24, i0=i, i1=i, t=b.t)
        else:
            cur["h"], cur["l"], cur["c"], cur["i1"] = max(cur["h"], b.h), min(cur["l"], b.l), b.c, i
    if cur:
        out.append(cur)
    return out


DEF = dict(keys=(1, 5, 9), max_inside=5, win_only=True, need_half=True, min_rr=2.0, buf=0.5, tp1_close=False,
           min_sl=3.0, max_sl=25.0, start=2, maxloss=2, max_day=2, entry="ob", d1_bias=False)


def setups(m5, h4, p, k):
    """Urdhrat limit: dict(t_from (fundi i C2), t_to (fundi i C3), side, px, sl, eq, tgt)."""
    out = []
    for n in range(len(h4) - 2):
        c1 = h4[n]
        if p["keys"] and c1["open_h"] not in p["keys"]:
            continue
        crh, crl = c1["h"], c1["l"]
        eq = crl + 0.5 * (crh - crl)
        j = n + 1
        while j < len(h4) and h4[j]["h"] <= crh and h4[j]["l"] >= crl and j - n <= p["max_inside"]:
            j += 1
        if j >= len(h4) - 1 or j - n > p["max_inside"]:
            continue
        c2 = h4[j]
        for sell in (True, False):
            if sell and not (c2["h"] > crh and crl < c2["c"] < crh and c2["l"] >= crl and (not p["need_half"] or c2["c"] > eq)):
                continue
            if not sell and not (c2["l"] < crl and crl < c2["c"] < crh and c2["h"] <= crh and (not p["need_half"] or c2["c"] < eq)):
                continue
            bars = range(c2["i0"], c2["i1"] + 1)
            ip = next(i for i in bars if (m5[i].h > crh if sell else m5[i].l < crl))     # purge-i
            hp = ny(m5[ip].t).hour
            if p["win_only"] and not (3 <= hp < 5 or 8 <= hp < 10):
                continue
            # ekstremi i sweep-it dhe CISD pas tij brenda C2
            ext = max(m5[i].h for i in bars) if sell else min(m5[i].l for i in bars)
            ie = next(i for i in bars if (m5[i].h == ext if sell else m5[i].l == ext))
            s = ie
            while s - 1 >= c2["i0"] and ((m5[s - 1].c > m5[s - 1].o) if sell else (m5[s - 1].c < m5[s - 1].o)):
                s -= 1
            if not ((m5[s].c > m5[s].o) if sell else (m5[s].c < m5[s].o)):
                # qiri i ekstremit s'eshte up-close: seria = qirinjte up-close me te fundit para tij
                s2 = ie - 1
                while s2 >= c2["i0"] and not ((m5[s2].c > m5[s2].o) if sell else (m5[s2].c < m5[s2].o)):
                    s2 -= 1
                if s2 < c2["i0"]:
                    continue
                s = s2
                while s - 1 >= c2["i0"] and ((m5[s - 1].c > m5[s - 1].o) if sell else (m5[s - 1].c < m5[s - 1].o)):
                    s -= 1
            lvl = m5[s].o
            cisd = any((m5[i].c < lvl) if sell else (m5[i].c > lvl) for i in range(ie, c2["i1"] + 1))
            if not cisd:
                continue
            c3 = h4[j + 1]
            px = lvl if p["entry"] == "ob" else None
            out.append(dict(t_from=m5[c2["i1"]].t + 300_000, t_to=m5[c3["i1"]].t + 300_000, side="SELL" if sell else "BUY",
                            px=px, sl=ext + p["buf"] * k if sell else ext - p["buf"] * k, eq=eq, tgt=crl if sell else crh,
                            c2_close=c2["c"]))
    return out


def run(m5, k=1.0, spread=0.2, p=None):
    p = dict(DEF, **(p or {}))
    h4 = h4_ny(m5)
    orders = sorted(setups(m5, h4, p, k), key=lambda o: o["t_from"])
    T, pos, per_day, loss_day, oi, live = [], None, {}, {}, 0, []
    for g in m5:
        L = lt(g.t)
        while oi < len(orders) and orders[oi]["t_from"] <= g.t:
            o = orders[oi]; oi += 1
            if p["entry"] == "mkt":          # hyrja "simple": ne treg ne hapjen pas mbylljes se C2
                o = dict(o, px=g.o, mkt=True)
            live.append(o)
        if pos:
            sell = pos["side"] == "SELL"
            o_, hi, lo = (g.o + spread, g.h + spread, g.l + spread) if sell else (g.o, g.h, g.l)
            x = None
            if L.weekday() >= 5 or (L.hour, L.minute) >= (22, 30):
                x = g.o + (spread if sell else 0)
            elif (sell and o_ >= pos["sl"]) or (not sell and o_ <= pos["sl"]):
                x = o_
            elif (sell and hi >= pos["sl"]) or (not sell and lo <= pos["sl"]):
                x = pos["sl"]
            elif (sell and lo <= pos["tp"]) or (not sell and hi >= pos["tp"]):
                x = pos["tp"]
            elif (sell and lo <= pos["eq"]) or (not sell and hi >= pos["eq"]):
                pos["sl"] = min(pos["sl"], pos["entry"] - spread) if sell else max(pos["sl"], pos["entry"] + spread)
            if x is not None:
                pnl = (pos["entry"] - x) if sell else (x - pos["entry"])
                pos.update(usd=pnl / k, r=pnl / pos["risk"])
                T.append(pos)
                if pnl < 0:
                    d = lt(pos["t"]).date(); loss_day[d] = loss_day.get(d, 0) + 1
                pos = None
        keep = []
        for o in live:
            sell = o["side"] == "SELL"
            if g.t >= o["t_to"] or ((g.l <= o["eq"]) if sell else (g.h >= o["eq"])) and not o.get("mkt"):
                continue                                   # C3 mbaroi ose EQ u prek para mbushjes
            hit = o.get("mkt") or ((g.h + spread >= o["px"]) if sell else (g.l <= o["px"]))
            if not hit:
                keep.append(o); continue
            if pos is not None or L.weekday() >= 5 or not (p["start"] <= L.hour < 22) or \
                    per_day.get(L.date(), 0) >= p["max_day"] or (p["maxloss"] and loss_day.get(L.date(), 0) >= p["maxloss"]):
                continue
            entry = o["px"] if not o.get("mkt") else (g.o + (0 if sell else spread))
            if (sell and entry >= o["sl"]) or (not sell and entry <= o["sl"]):
                continue
            risk = max(abs(o["sl"] - entry), p["min_sl"] * k)
            rew = (entry - o["tgt"]) if sell else (o["tgt"] - entry)
            if risk > p["max_sl"] * k or rew < p["min_rr"] * risk:
                continue
            tp = o["eq"] if p["tp1_close"] else o["tgt"]
            pos = dict(side=o["side"], entry=entry, risk=risk, t=g.t, eq=o["eq"], tp=tp,
                       sl=entry + risk if sell else entry - risk)
            per_day[L.date()] = per_day.get(L.date(), 0) + 1
        live = keep
    return T


if __name__ == "__main__":
    G = pickle.load(open(sys.argv[1], "rb"))
    V = eval(sys.argv[2]) if len(sys.argv) > 2 else {"CRT konservative": {}}
    for name, kw in V.items():
        R = {}
        for y in range(2016, 2027):
            t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            t1 = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            g = [b for b in G if t0 - 3 * 86400000 <= b.t < t1]
            k = 1.0 if y == 2026 else statistics.median(b.c for b in g) / 4513.71
            R[y] = [x for x in run(g, k, 0.2 * k, kw) if t0 <= x["t"] < t1]
        H = [x for y, v in R.items() if y < 2026 for x in v]
        print(f"{name:30} | 2026 {stats(R[2026])} | 10v {stats(H)} | " +
              " ".join(f"{y % 100}:{sum(x['usd'] for x in v):+.0f}" for y, v in sorted(R.items())), flush=True)
