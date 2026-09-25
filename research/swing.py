"""Prototip kerkimi: setup-i "swing sniper" i pronarit (shembulli 4 gusht 2026, BUY ~4047).

BUY (SELL eshte pasqyra):
  H4   support i forte: nje zone demand H4 qe s'eshte thyer (asnje mbyllje H4 nen te)
  H1   divergjence AO: swing low-i i ri H1 (koka) brenda zones H4 eshte me i ulet se swing low-i
       para tij, por AO eshte me i larte
  M15  supply-i M15 me i afert mbi koke thyhet (mbyllje M15 mbi te) -> behet demand
  M15  cmimi e riteston supply-n e thyer dhe mbyllet me wick poshte -> hyrje ne mbyllje
  SL   poshte qirit te rejection-it; TP1/TP2/TP3 te zonat supply D1 lart (e fundit = supply-i
       dominant qe solli renien e madhe)
Ekzekuto nga rrenja e repo-s: python -m research.swing <m5.pkl>
"""
import sys
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.hierarchy import ao_series
from bot.zones import SRV, aggregate, find_zones, swings, with_flips

H1, M15 = 3_600_000, 900_000
SPREAD = 0.2


@dataclass
class P:
    disp: float = 1.5
    h4_tol: float = 3.0          # $: sa jashte zones H4 lejohet koka
    h4_age_days: float = 60
    div_look: int = 120          # qirinj H1 mbrapa per swing-un e divergjences
    swing_k: int = 2
    window_h: float = 48         # sa ore pas konfirmimit te kokes pritet thyerja + retest-i
    touch_tol: float = 0.0       # $: retest-i duhet te preke zonen e thyer
    max_zone_h: float = 8.0      # $: zonat M15 me te gjera se kaq nuk perdoren
    max_entries: int = 1         # sa hyrje lejohen per nje divergjence H1
    sweep: bool = False          # rejection-i duhet te kaloje me wick pertej zones dhe te mbyllet brenda
    flip_gens: int = 3           # sa here mund te kthehet nje zone (demand -> supply -> demand ...)
    rej_wick: float = 0.5
    sl_buf: float = 0.5
    min_sl: float = 3.0
    max_sl: float = 20.0
    min_rr: float = 2.0
    d1_fresh: bool = False       # TP vetem te zona D1 te paprekura
    tp_merge: float = 5.0        # $: zonat D1 me afer se kaq bashkohen ne nje objektiv
    start_h: int = 1
    end_h: int = 20


def prepare(m5, p: P):
    m15 = aggregate(m5, 15)
    h1 = aggregate(m5, 60)
    h4 = aggregate(m5, 240, SRV)
    d1 = aggregate(m5, 1440, SRV)
    z4 = with_flips(find_zones(h4, 4 * H1, p.disp, tf="H4"), h4, 4 * H1)
    # zonat e thyera M15, edhe ato qe thyhen disa here (demand -> supply -> demand)
    gen = find_zones(m15, M15, p.disp, tf="M15")
    z15 = []
    for _ in range(p.flip_gens):
        gen = with_flips(gen, m15, M15)[len(gen):]
        z15 += gen
    zd = with_flips(find_zones(d1, 24 * H1, p.disp, tf="D1"), d1, 24 * H1)
    return dict(m15=m15, h1=h1, z4=z4, z15=z15, zd=zd, ao=ao_series(h1), sw=swings(h1, p.swing_k))


def setups(m5, p: P, ind):
    """Hyrjet: dict(t, side, entry_c, sl_raw, head, tps)."""
    m15, h1, z4, z15, zd, ao, sw = (ind[k] for k in ("m15", "h1", "z4", "z15", "zd", "ao", "sw"))
    age = p.h4_age_days * 86_400_000
    lows, highs = [], []
    armed, out = [], []
    si = 0
    h1_close = [b.t + H1 for b in h1]
    for j, b in enumerate(m15):
        t_close = b.t + M15
        # swing-et H1 te konfirmuara deri ne mbylljen e ketij qiri M15
        while si < len(sw) and h1_close[sw[si][0]] <= t_close:
            c, i, k, v = sw[si]
            si += 1
            src = lows if k == "L" else highs
            prev = [x for x in src if i - x[0] <= p.div_look]
            src.append((i, v))
            buy = k == "L"
            want = "D" if buy else "S"
            walls = [z for z in z4 if z.kind == want and z.known <= h1[i].t and z.dead > h1[c].t
                     and h1[i].t - z.known <= age and z.lo - p.h4_tol <= v <= z.hi + p.h4_tol]
            if not walls or not prev or ao[i] != ao[i]:
                continue
            pi, pv = prev[-1]
            if ao[pi] != ao[pi]:
                continue
            div = (v < pv and ao[i] > ao[pi]) if buy else (v > pv and ao[i] < ao[pi])
            if div:
                armed.append(dict(side="BUY" if buy else "SELL", head=v, head_t=h1[i].t, t0=h1_close[c], used=0))
        armed = [a for a in armed if a["used"] < p.max_entries and t_close - a["t0"] <= p.window_h * H1
                 and not ((a["side"] == "BUY" and b.c < a["head"]) or (a["side"] == "SELL" and b.c > a["head"]))]
        rng = b.h - b.l
        if rng <= 0:
            continue
        for a in armed:
            buy = a["side"] == "BUY"
            kind = "D" if buy else "S"      # supply i thyer -> demand (BUY)
            zs = [z for z in z15 if z.kind == kind and a["head_t"] < z.known <= b.t and z.dead > b.t
                  and z.hi - z.lo <= p.max_zone_h and ((buy and z.lo > a["head"]) or (not buy and z.hi < a["head"]))]
            if buy:
                zs = [z for z in zs if b.l <= z.hi + p.touch_tol and b.c >= z.lo and (not p.sweep or b.l < z.lo)]
                rej = (min(b.o, b.c) - b.l) / rng >= p.rej_wick and b.c > (b.h + b.l) / 2
            else:
                zs = [z for z in zs if b.h >= z.lo - p.touch_tol and b.c <= z.hi and (not p.sweep or b.h > z.hi)]
                rej = (b.h - max(b.o, b.c)) / rng >= p.rej_wick and b.c < (b.h + b.l) / 2
            if not zs or not rej:
                continue
            a["used"] += 1
            opp = "S" if buy else "D"
            lv = sorted((z.lo if buy else z.hi) for z in zd if z.kind == opp and z.known <= t_close
                        and z.dead > b.t and (not p.d1_fresh or z.first_touch >= b.t)
                        and ((buy and z.lo > b.c) or (not buy and z.hi < b.c)))
            if not buy:
                lv = lv[::-1]
            tps = []
            for x in lv:
                if not tps or abs(x - tps[-1]) > p.tp_merge:
                    tps.append(x)
            out.append(dict(t=t_close, side=a["side"], entry_c=b.c, head=a["head"],
                            sl_raw=(b.l - p.sl_buf) if buy else (b.h + p.sl_buf), tps=tps, zone=(zs[0].lo, zs[0].hi)))
    return out


def trade(m5, s, p: P, tp_n=1, split=False, be_after_tp1=False, weekend="close", cap_days=30):
    """Dalja ne M5. tp_n: cili objektiv D1 (1, 2, 3); split: 1/3 ne secilin nga TP1-TP3.
    weekend: "close" = mbyll te premten 19:00 UTC, "hold" = mban (gap-i llogaritet)."""
    import bisect
    buy = s["side"] == "BUY"
    entry = s["entry_c"] + (SPREAD if buy else 0)
    risk = max(abs(entry - s["sl_raw"]), p.min_sl)
    if risk > p.max_sl:
        return None
    tps = [x for x in s["tps"] if (x - entry if buy else entry - x) >= p.min_rr * risk]
    if not tps:
        return None
    if split:
        tps = (tps + [tps[-1]] * 3)[:3]
        parts = [[x, 1 / 3, None] for x in tps]
    else:
        if len(tps) < tp_n:
            tps = tps + [tps[-1]] * (tp_n - len(tps))
        parts = [[tps[tp_n - 1], 1.0, None]]
    sl = entry - risk if buy else entry + risk
    i0 = bisect.bisect_left([b.t for b in m5], s["t"])
    t_exit = m5[-1].t
    end = s["t"] + cap_days * 86_400_000
    for b in m5[i0:]:
        t_exit = b.t
        lo, hi = (b.l, b.h) if buy else (b.l + SPREAD, b.h + SPREAD)
        d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
        if weekend == "close" and ((d.weekday() == 4 and d.hour >= 19) or d.weekday() >= 5):
            for q in parts:
                if q[2] is None:
                    q[2] = b.o
            break
        # gap-i i se henes: hapja pertej SL mbyllet ne hapje
        if (buy and b.o <= sl) or (not buy and b.o + (0 if buy else SPREAD) >= sl):
            for q in parts:
                if q[2] is None:
                    q[2] = b.o + (0 if buy else SPREAD)
            break
        if (buy and lo <= sl) or (not buy and hi >= sl):
            for q in parts:
                if q[2] is None:
                    q[2] = sl
            break
        hit1 = False
        for q in parts:
            if q[2] is None and ((buy and hi >= q[0]) or (not buy and lo <= q[0])):
                q[2] = q[0]
                hit1 = True
        if hit1 and be_after_tp1:
            sl = max(sl, entry) if buy else min(sl, entry)
        if all(q[2] is not None for q in parts) or b.t >= end:
            for q in parts:
                if q[2] is None:
                    q[2] = b.c
            break
    r = sum(((q[2] if q[2] is not None else m5[-1].c) - entry if buy else entry - (q[2] if q[2] is not None else m5[-1].c)) * q[1]
            for q in parts) / risk
    return dict(t=s["t"], exit_t=t_exit, side=s["side"], r=r, entry=entry, risk=risk, tps=[q[0] for q in parts])


def run(m5, p: P, ind=None, **kw):
    ind = ind or prepare(m5, p)
    T, busy = [], 0
    for s in setups(m5, p, ind):
        hr = datetime.fromtimestamp(s["t"] / 1000, timezone.utc)
        if s["t"] < busy or not (p.start_h <= hr.hour < p.end_h) or hr.weekday() >= 5 or (hr.weekday() == 4 and hr.hour >= 19):
            continue
        x = trade(m5, s, p, **kw)
        if x:
            T.append(x)
            busy = x["exit_t"]
    return T


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    p = P()
    ind = prepare(m5, p)
    for s in setups(m5, p, ind):
        d = datetime.fromtimestamp(s["t"] / 1000, timezone.utc)
        if d.month == 8 and d.day <= 6:
            print(d, s["side"], round(s["entry_c"], 2), "SL", round(s["sl_raw"], 2), "koka", s["head"], "zona", s["zone"], "TP", [round(x, 1) for x in s["tps"][:4]])
    T = run(m5, p, ind)
    print(len(T), "trade", f"{sum(x['r'] for x in T):+.1f}R")

# Rezultati (M5 nga llogaria, 26 jan - 25 sht 2026), P(max_entries=3, window_h=24, sweep=True):
#   Shembulli i pronarit kapet saktesisht: BUY 4 gusht 01:15 UTC @ 4047.14, SL 4042.11 (nen wick-un
#   4042.61 qe kaloi poshte zones M15 4045.51-4049.81, e thyer dy here). Objektivat D1 ne hyrje:
#   4154 (+21R), 4259, 4328 (+56R), 4438, 4650 (+120R), 4689 = supply-i dominant (+128R, 25 gusht).
#   Cmimi s'ra me nen 4045.60 pas hyrjes.
#   Por me te njejtat rregulla 8 muajt japin 41 trade, 5 fitime: TP3 +34.7R, TP1 +2.7R, TP2 +23.6R.
#   Pa 4 gushtin (+55.8R) 40 trade-t e tjera japin -21R; shk-maj eshte negativ ne cdo variant.
#   Pa kerkesen "sweep" (wick pertej zones): 26-40 trade, -31R deri +5R. Nuk u shtua ne botin live.
