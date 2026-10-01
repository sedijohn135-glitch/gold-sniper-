"""ICT / Quarterly Theory (Daye) ne XAUUSD me argjendin (XAGUSD) si aset i lidhur.

Te dhenat: M5 nga cTrader (IC Markets) per te dy asetet, i njejti burim -> qirinj te sinkronizuar.
CIKLI: dita fillon 18:00 ora e New York-ut; ndahet ne cereke: 90 min (cikli i seances), 6 ore (seancat Asia/London/
NY/PM) ose 1 dite. Cereku i meparshem jep high/low (ERL = likuiditeti i jashtem).
SSMT (sequential SMT, SELL; BUY = pasqyra): brenda cerekut aktual njeri aset kalon high-in e cerekut te meparshem
  ndersa tjetri jo ("crack in correlation"): ari kalon dhe argjendi jo, ose argjendi kalon dhe ari jo.
PSP / CISD (hyrja): pas SSMT, qiri i pare M5 i arit qe mbyllet nen hapjen e qirit te fundit bullish para majes
  (change in state of delivery), brenda `win` qirinjve; hyrje ne hapjen e qirit tjeter.
SL: maja e cerekut (sweep) + `buf` $. TP: low-i i cerekut te meparshem (ERL) nese >= `min_rr` R, ndryshe `rr` R.
Filtri premium/discount (opsional): SELL vetem mbi hapjen e vertete te dites (00:00 NY), BUY vetem nen te.
Rregullat e botit: hyrje 02:00-22:00 ora e Shqiperise, mbyllje 22:30, 1 pozicion, max 4/dite, stop pas 2 humbjeve, BE 1R.

    python -m research.qt_smt <ct_XAUUSD_m5.pkl> <ct_XAGUSD_m5.pkl> [variantet]
"""
import pickle
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from bot.report import local

NY = ZoneInfo("America/New_York")
M5 = 300_000


@dataclass
class P:
    cycle: int = 90          # minuta: 90 / 360 / 1440
    win: int = 12            # qirinj M5 per CISD pas SSMT
    buf: float = 0.5
    tp: str = "erl"          # erl / rr
    rr: float = 2.0
    min_rr: float = 1.5
    tdo: bool = False
    who: str = "any"         # any / gold (ari kalon, argjendi jo) / silver (argjendi kalon, ari jo)
    min_sl: float = 3.0
    max_sl: float = 25.0
    start: int = 2
    maxloss: int = 2
    be: float = 1.0


def lt(t):
    return local(datetime.fromtimestamp(t / 1000, timezone.utc))


def qkey(t, cycle):
    ny = datetime.fromtimestamp(t / 1000, NY)
    base = ny - timedelta(hours=18)                      # dita e ciklit fillon 18:00 NY
    mins = base.hour * 60 + base.minute
    return (base.date(), mins // cycle)


def align(g, s):
    sd = {b.t: b for b in s}
    G, S = [], []
    for b in g:
        x = sd.get(b.t)
        if x is not None:
            G.append(b); S.append(x)
    return G, S


def run(G, Sv, k=1.0, spread=0.2, p=P()):
    T, pos, per_day, loss_day = [], None, {}, {}
    q_prev = q_cur = None          # dict(key, gh, gl, sh, sl)
    tdo, tdo_day = None, None
    setup = None                    # SSMT ne pritje te CISD
    last_bull = last_bear = None    # qiri i fundit bullish/bearish i arit (hapja)
    for j, (g, s) in enumerate(zip(G, Sv)):
        L = lt(g.t)
        nyd = datetime.fromtimestamp(g.t / 1000, NY)
        if nyd.date() != tdo_day and nyd.hour == 0:
            tdo, tdo_day = g.o, nyd.date()
        # ---- pozicioni ----
        if pos:
            sell = pos["side"] == "SELL"
            o, hi, lo = (g.o + spread, g.h + spread, g.l + spread) if sell else (g.o, g.h, g.l)
            x = None
            if L.weekday() >= 5 or (L.hour, L.minute) >= (22, 30):
                x = g.o + (spread if sell else 0)
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
                pos.update(usd=pnl / k, r=pnl / pos["risk"], exit_t=g.t)
                T.append(pos)
                if pnl < 0:
                    d = lt(pos["t"]).date(); loss_day[d] = loss_day.get(d, 0) + 1
                pos = None
        # ---- cereku ----
        key = qkey(g.t, p.cycle)
        if q_cur is None or key != q_cur["key"]:
            q_prev, q_cur = q_cur, dict(key=key, gh=g.h, gl=g.l, sh=s.h, sl=s.l, gh_j=j, gl_j=j)
            setup = None
        else:
            if g.h > q_cur["gh"]:
                q_cur["gh"], q_cur["gh_j"] = g.h, j
            if g.l < q_cur["gl"]:
                q_cur["gl"], q_cur["gl_j"] = g.l, j
            q_cur["sh"], q_cur["sl"] = max(q_cur["sh"], s.h), min(q_cur["sl"], s.l)
        # ---- CISD per setup-in ekzistues (perpara se te azhurnohet qiri i fundit bullish/bearish) ----
        if setup and j - setup["j"] <= p.win:
            sell = setup["side"] == "SELL"
            ref = setup["ref"]
            if ref is not None and ((sell and g.c < ref) or (not sell and g.c > ref)) and j + 1 < len(G):
                nb = G[j + 1]; NL = lt(nb.t)
                ok = pos is None and NL.weekday() < 5 and p.start <= NL.hour < 22 and per_day.get(NL.date(), 0) < 4 \
                    and not (p.maxloss and loss_day.get(NL.date(), 0) >= p.maxloss)
                if ok and p.tdo and tdo is not None and ((sell and g.c < tdo) or (not sell and g.c > tdo)):
                    ok = False
                if ok:
                    entry = nb.o + (0 if sell else spread)
                    ext = q_cur["gh"] if sell else q_cur["gl"]
                    slp = ext + p.buf * k if sell else ext - p.buf * k
                    risk = max(abs(slp - entry), p.min_sl * k)
                    if risk <= p.max_sl * k and ((sell and slp > entry) or (not sell and slp < entry)):
                        erl = q_prev["gl"] if sell else q_prev["gh"]
                        tp = erl if (p.tp == "erl" and ((sell and entry - erl >= p.min_rr * risk) or
                                                         (not sell and erl - entry >= p.min_rr * risk))) else \
                            (entry - p.rr * risk if sell else entry + p.rr * risk)
                        pos = dict(side=setup["side"], entry=entry, risk=risk, t=nb.t, who=setup["who"],
                                   sl=entry + risk if sell else entry - risk, tp=tp)
                        per_day[NL.date()] = per_day.get(NL.date(), 0) + 1
                setup = None
        elif setup:
            setup = None
        # ---- SSMT: njeri kalon high/low-in e cerekut te meparshem, tjetri jo ----
        if q_prev is not None and setup is None:
            g_up, s_up = q_cur["gh"] > q_prev["gh"], q_cur["sh"] > q_prev["sh"]
            g_dn, s_dn = q_cur["gl"] < q_prev["gl"], q_cur["sl"] < q_prev["sl"]
            new_hi = g.h >= q_cur["gh"] or s.h >= q_cur["sh"]
            new_lo = g.l <= q_cur["gl"] or s.l <= q_cur["sl"]
            if new_hi and g_up != s_up and (p.who == "any" or (p.who == "gold") == g_up):
                setup = dict(side="SELL", j=j, ref=last_bull if not (g.c > g.o) else g.o, who="gold" if g_up else "silver")
            elif new_lo and g_dn != s_dn and (p.who == "any" or (p.who == "gold") == g_dn):
                setup = dict(side="BUY", j=j, ref=last_bear if not (g.c < g.o) else g.o, who="gold" if g_dn else "silver")
        if g.c > g.o:
            last_bull = g.o
        elif g.c < g.o:
            last_bear = g.o
    return T


def stats(T):
    eq = pk = dd = 0
    for x in sorted(T, key=lambda x: x["t"]):
        eq += x["usd"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    w = sum(x["r"] > 0.05 for x in T)
    return f"{len(T):5} tr {sum(x['usd'] for x in T):+7.0f}$ DD {dd:5.0f}$ fit {w / max(len(T), 1):4.0%}"


def evaluate(G, Sv, p):
    """2026 (k=1) dhe 2016-2025 vit per vit me shkallen e cmimit."""
    out = {}
    for y in range(2016, 2027):
        t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        t1 = datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        idx = [i for i, b in enumerate(G) if t0 - 2 * 86400000 <= b.t < t1]
        if not idx:
            continue
        g, s = G[idx[0]:idx[-1] + 1], Sv[idx[0]:idx[-1] + 1]
        k = 1.0 if y == 2026 else statistics.median(b.c for b in g) / 4513.71
        out[y] = [x for x in run(g, s, k=k, spread=0.2 * k, p=p) if t0 <= x["t"] < t1]
    return out


if __name__ == "__main__":
    G, Sv = align(pickle.load(open(sys.argv[1], "rb")), pickle.load(open(sys.argv[2], "rb")))
    V = eval(sys.argv[3]) if len(sys.argv) > 3 else {"90 min": {}}
    for name, kw in V.items():
        R = evaluate(G, Sv, P(**kw))
        H = [x for y, v in R.items() if y < 2026 for x in v]
        print(f"{name:34} | 2026 {stats(R.get(2026, []))} | 10v {stats(H)} | " +
              " ".join(f"{y % 100}:{sum(x['usd'] for x in v):+.0f}" for y, v in sorted(R.items())), flush=True)
