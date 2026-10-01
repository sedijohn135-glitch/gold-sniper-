"""Motori SNR Malajzian (MSNR) dhe backtest-i i setup-it baze (KororFX / Emperor 7 / SNR Malaysia / Rare SnR).

NIVELET (nga TRUPI i qirinjve, bishtat injorohen), te nderuara ne nje TF (H4 ose D1):
  A   = qiri bullish pastaj qiri bearish: rezistence ne mbylljen e qirit te pare
  V   = qiri bearish pastaj qiri bullish: support ne mbylljen e qirit te pare
  GAP = si A/V, por qiri i dyte eshte momentum: mbyllet pertej hapjes se te parit (zona e fshehur)
  Niveli njihet vetem pasi mbyllet qiri i dyte.
GJENDJA:
  fresh   = asnje bisht s'e ka prekur qe kur u krijua (ose qe kur u flip-ua)
  prekje  = cmimi (cdo qiri M15) e prek nivelin -> unfresh; perdoret max `uses` here
  thyerje = qiri i TF-se se nivelit MBYLLET pertej -> flip (A -> RBS support, V -> SBR rezistence), fresh perseri
  MISS    = `miss` qirinjte e pare te TF-se pas krijimit s'e prekin nivelin (e validon)
SETUP-I (SELL, BUY = pasqyra) - "2 TF's confirmation" / "1-2 TF lower breakout":
  1. M15 prek nje rezistence fresh (ose te perdorur < uses here) te H4/D1.
  2. Pas prekjes, M15 MBYLLET nen low-in me te ulet te `pre` qirinjve M15 para prekjes (thyerje strukture LTF)
     brenda `bo_bars` qirinjve, pa asnje mbyllje M15 mbi nivel + tolerance (perndryshe niveli s'mbajti).
  3. Hyrja: 'mkt' = ne mbyllje te qirit te thyerjes; 'retest' = limit te niveli i thyer (low-i), brenda `rt_bars`.
  4. SL = maja e prekjes + buffer (min/max ne $), TP = RR fiks ose niveli fresh i kundert i HTF-se; BE ne 1R;
     mbyllje 22:30, hyrje 02:00-22:00 ora e Shqiperise, 1 pozicion, max 4 trade/dite, stop pas 2 humbjeve.
Ekzekutimi: qirinj M15 (SL para TP ne te njejtin qiri; SL e kaluar ne hapje mbushet ne hapje).

    python -m research.msnr <hist_m5.pkl> <m5_2026.pkl> [varianti]
"""
import pickle
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bot.report import local
from bot.strategy import Bar
from bot.zones import aggregate

M15 = 900_000


@dataclass
class Level:
    p: float
    res: bool            # True = rezistence (SELL), False = support (BUY)
    typ: str             # A / V / GAP / RBS / SBR
    tf: str
    born: int            # koha kur njihet (ms)
    touches: int = 0
    miss_ok: bool = False
    flips: int = 0
    seen: int = 0        # sa qirinj te TF-se kane kaluar qe nga krijimi/flip-i
    miss1: bool = False  # qiri i pare i TF-se pas krijimit s'e preku nivelin


def make_levels(bars, tf_ms, tf):
    """Nivelet A/V/GAP nga ciftet e qirinjve (mbyllja e te parit)."""
    out = []
    for i in range(1, len(bars)):
        a, b = bars[i - 1], bars[i]
        if a.c > a.o and b.c < b.o:
            out.append(Level(a.c, True, "GAP" if b.c < a.o else "A", tf, b.t + tf_ms))
        elif a.c < a.o and b.c > b.o:
            out.append(Level(a.c, False, "GAP" if b.c > a.o else "V", tf, b.t + tf_ms))
    return out


def xfactor(c, j, lvl, res, tol, k=3, look=96):
    """X factor: vija qe bashkon dy majat (per rezistence) ose dy fundet e fundit te grafikut me vije (mbylljet M15,
    te konfirmuara k qirinj me pas) kalon, ne qirin j, brenda `tol` nga niveli (TL x SNR ne te njejten pike)."""
    pts = []
    for i in range(j - k - 1, max(k, j - look) - 1, -1):
        w = c[i - k:i + k + 1]
        if (res and c[i] == max(w)) or (not res and c[i] == min(w)):
            pts.append(i)
            if len(pts) == 2:
                break
    if len(pts) < 2:
        return False
    i2, i1 = pts                      # i1 me i hershem
    slope = (c[i2] - c[i1]) / (i2 - i1)
    if (res and slope >= 0) or (not res and slope <= 0):   # TL rezistence zbret, TL support ngjitet
        pass
    return abs(c[i2] + slope * (j - i2) - lvl) <= tol


def lt(t):
    return local(datetime.fromtimestamp(t / 1000, timezone.utc))


@dataclass
class P:
    htf: tuple = ("H4", "D1")
    uses: int = 1          # sa prekje lejohen (1 = vetem prekja e pare e nivelit fresh)
    miss: int = 0          # sa qirinj HTF pas krijimit duhet ta "humbasin" nivelin (0 = pa kusht)
    types: tuple = ("A", "V", "GAP", "RBS", "SBR")
    pre: int = 8           # qirinjte M15 para prekjes qe japin strukturen per thyerje
    bo_bars: int = 16      # sa qirinj M15 pret per thyerjen
    entry: str = "mkt"     # mkt / retest
    rt_bars: int = 16
    tp: str = "rr"         # rr / level
    rr: float = 3.0
    buf: float = 0.5       # $ mbi majen e prekjes
    tol: float = 0.5       # $ tolerance per mbylljen mbi nivel
    sl: str = "ext"        # ext = pas majes se prekjes; level = pas nivelit + lbuf (KororFX: 20 pips)
    lbuf: float = 2.0
    strict: bool = False
    need_miss: bool = False
    need_story: bool = False
    need_xf: bool = False
    kz: bool = False   # True = edhe nje mbyllje M15 pertej nivelit e anulon setup-in
    max_age_d: float = 30  # nivelet me te vjetra s'perdoren
    min_sl: float = 3.0
    max_sl: float = 25.0
    start: int = 2
    maxloss: int = 2
    be: float = 1.0


def run(m15, htf_bars, k=1.0, spread=0.2, p=P()):
    """m15: qirinjte M15; htf_bars: {'H4': [...], 'D1': [...]}. Kthen listen e trade-ve."""
    tf_ms = {"H4": 4 * 3_600_000, "D1": 86_400_000, "H1": 3_600_000}
    pend_lv = []
    for tf in p.htf:
        pend_lv += make_levels(htf_bars[tf], tf_ms[tf], tf)
    pend_lv.sort(key=lambda x: x.born)
    # mbylljet e qirinjve HTF sipas kohes se perfundimit
    closes = {}
    for tf in p.htf:
        for b in htf_bars[tf]:
            closes.setdefault(b.t + tf_ms[tf], []).append((tf, b))
    active, li = [], 0
    story = [0]
    # pikat e grafikut me vije (mbyllje M15): maja/fund lokal me k=3 nga secila ane, te njohura 3 qirinj me vone
    closes_c = [x.c for x in m15]
    setups = []          # setup-et ne pritje: dict
    T, pos, per_day, loss_day = [], None, {}, {}

    def ok(f):
        if p.need_miss and not f["miss1"]: return False
        if p.need_story and f["story"] < 1: return False
        if p.need_xf and not f["xf"]: return False
        if p.kz and not (8 <= f["hour"] < 11 or 13 <= f["hour"] < 17): return False
        return True
    minsl, maxsl, buf, tol = p.min_sl * k, p.max_sl * k, p.buf * k, p.tol * k
    max_age = p.max_age_d * 86_400_000

    def close_pos(b, px, why):
        nonlocal pos
        sell = pos["side"] == "SELL"
        x = px + (spread if sell else 0)
        pnl = (pos["entry"] - x) if sell else (x - pos["entry"])
        pos.update(exit_t=b.t, why=why, usd=pnl / k, r=pnl / pos["risk"])
        T.append(pos)
        if pnl < 0:
            d = lt(pos["t"]).date()
            loss_day[d] = loss_day.get(d, 0) + 1
        pos = None

    FEAT = [{}]

    def open_pos(b_next, side, entry, sl_px, lv, t):
        nonlocal pos
        if p.sl == "level":
            sl_px = lv.p + p.lbuf * k if side == "SELL" else lv.p - p.lbuf * k
        L = lt(t)
        if L.weekday() >= 5 or not (p.start <= L.hour < 22) or per_day.get(L.date(), 0) >= 4:
            return False
        if p.maxloss and loss_day.get(L.date(), 0) >= p.maxloss:
            return False
        sell = side == "SELL"
        risk = max(abs(sl_px - entry), minsl)
        if risk > maxsl:
            return False
        sl = entry + risk if sell else entry - risk
        if p.tp == "rr":
            tp = entry - p.rr * risk if sell else entry + p.rr * risk
        else:   # niveli fresh i kundert me i afert, me RR >= 1.5
            cands = [x.p for x in active if x.res != sell and x.touches == 0 and
                     ((sell and x.p < entry - 1.5 * risk) or (not sell and x.p > entry + 1.5 * risk))]
            if not cands:
                tp = entry - p.rr * risk if sell else entry + p.rr * risk
            else:
                tp = max(cands) if sell else min(cands)
        pos = dict(side=side, entry=entry, sl=sl, tp=tp, risk=risk, t=t, lv=lv.p, typ=lv.typ, tf=lv.tf, **FEAT[0])
        per_day[L.date()] = per_day.get(L.date(), 0) + 1
        return True

    for j, b in enumerate(m15):
        end = b.t + M15
        L = lt(b.t)
        # ---- menaxho pozicionin ----
        if pos:
            sell = pos["side"] == "SELL"
            o, hi, lo = (b.o + spread, b.h + spread, b.l + spread) if sell else (b.o, b.h, b.l)
            if L.weekday() >= 5 or (L.hour, L.minute) >= (22, 30):
                close_pos(b, b.o, "22:30")
            elif (sell and o >= pos["sl"]) or (not sell and o <= pos["sl"]):
                close_pos(b, b.o, "gap")
            elif (sell and hi >= pos["sl"]) or (not sell and lo <= pos["sl"]):
                close_pos(b, pos["sl"] - (spread if sell else 0), "SL")
            elif (sell and lo <= pos["tp"]) or (not sell and hi >= pos["tp"]):
                close_pos(b, pos["tp"] - (spread if sell else 0), "TP")
            else:
                fav = (pos["entry"] - lo) if sell else (hi - pos["entry"])
                if p.be and fav >= p.be * pos["risk"]:
                    pos["sl"] = min(pos["sl"], pos["entry"] - spread) if sell else max(pos["sl"], pos["entry"] + spread)
        # ---- nivelet e reja qe njihen tani ----
        while li < len(pend_lv) and pend_lv[li].born <= b.t:
            active.append(pend_lv[li]); li += 1
        # ---- prekjet (cdo qiri M15) ----
        for lv in active:
            if (lv.res and b.h >= lv.p) or (not lv.res and b.l <= lv.p):
                if lv.touches < p.uses and lv.typ in p.types and (lv.miss_ok or p.miss == 0) and \
                        b.t - lv.born <= max_age:
                    m = 4 if lv.tf == "D1" else 1          # D1 -> thyerje H1, H4 -> thyerje M15 (2 TF me poshte)
                    pre = m15[max(0, j - p.pre * m):j] or [b]
                    feat = dict(miss1=lv.miss1, story=story[0] * (-1 if lv.res else 1), age_h=(b.t - lv.born) / 3.6e6,
                                xf=xfactor(closes_c, j, lv.p, lv.res, 1.5 * k), hour=lt(b.t).hour)
                    setups.append(dict(lv=lv, j=j, m=m, flips=lv.flips, feat=feat, ext=b.h if lv.res else b.l,
                                       brk=min(x.l for x in pre) if lv.res else max(x.h for x in pre)))
                lv.touches += 1
        # ---- setup-et ne pritje: thyerja LTF, pastaj hyrja ----
        keep = []
        for s in setups:
            lv, sell = s["lv"], s["lv"].res
            if "fill_from" not in s:
                s["ext"] = max(s["ext"], b.h) if sell else min(s["ext"], b.l)
                if lv.flips != s["flips"] or (p.strict and ((sell and b.c > lv.p + tol) or (not sell and b.c < lv.p - tol))):
                    continue                      # niveli s'mbajti (HTF mbylli pertej / M15 mbylli pertej)
                if j - s["j"] > p.bo_bars * s["m"]:
                    continue
                if (sell and b.c < s["brk"]) or (not sell and b.c > s["brk"]):
                    if p.entry == "mkt":
                        if pos is None and j + 1 < len(m15) and ok(s["feat"]):
                            FEAT[0] = s["feat"]; nb = m15[j + 1]
                            open_pos(nb, "SELL" if sell else "BUY", nb.o + (0 if sell else spread),
                                     s["ext"] + buf if sell else s["ext"] - buf, lv, nb.t)
                        continue
                    s["fill_from"] = j
                keep.append(s)
            else:
                if j - s["fill_from"] > p.rt_bars * s["m"] or (sell and b.h > s["ext"]) or (not sell and b.l < s["ext"]):
                    continue
                px = s["brk"]
                if j > s["fill_from"] and ((sell and b.h + spread >= px) or (not sell and b.l <= px - spread)):
                    if pos is None and ok(s["feat"]):
                        FEAT[0] = s["feat"]
                        open_pos(b, "SELL" if sell else "BUY", px, s["ext"] + buf if sell else s["ext"] - buf, lv, b.t)
                    continue
                keep.append(s)
        setups = keep
        # ---- mbylljet e qirinjve HTF: miss, thyerje/flip, plakja ----
        for tf, hb in closes.get(end, []):
            for lv in active:
                if lv.tf != tf or lv.born > hb.t:
                    continue
                lv.seen += 1
                if lv.seen == 1 and lv.touches == 0:
                    lv.miss1 = True
                if tf == "D1" and ((lv.res and hb.c > lv.p) or (not lv.res and hb.c < lv.p)):
                    story[0] = 1 if lv.res else -1     # storyline D1: drejtimi i thyerjes se fundit me trup
                if lv.seen <= max(p.miss, 0) and lv.touches == 0 and lv.seen == p.miss:
                    lv.miss_ok = True
                if (lv.res and hb.c > lv.p) or (not lv.res and hb.c < lv.p):
                    lv.res = not lv.res
                    lv.typ = "RBS" if not lv.res else "SBR"
                    lv.touches, lv.seen, lv.flips, lv.miss_ok = 0, 0, lv.flips + 1, False
                    lv.born = end
            active = [x for x in active if end - x.born <= max_age and x.flips <= 2]
    return T


def run_live(m15, htf_bars, k=1.0, spread=0.2, p=None, start=2, maxloss=2, be=1.0):
    """Backtest me te njejtin motor sinjalesh si boti live (bot/msnr.py), hyrje ne treg."""
    import bot.msnr as LM
    p = p or LM.P()
    ev = {}
    for s in LM.scan(m15, htf_bars, p, k):
        ev.setdefault(s["j"], []).append(s)
    T, pos, per_day, loss_day = [], None, {}, {}
    for j, b in enumerate(m15):
        L = lt(b.t)
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
                if be and fav >= be * pos["risk"]:
                    pos["sl"] = min(pos["sl"], pos["entry"] - spread) if sell else max(pos["sl"], pos["entry"] + spread)
            if x is not None:
                pnl = (pos["entry"] - x) if sell else (x - pos["entry"])
                pos.update(usd=pnl / k, r=pnl / pos["risk"], exit_t=b.t)
                T.append(pos)
                if pnl < 0:
                    loss_day[lt(pos["t"]).date()] = loss_day.get(lt(pos["t"]).date(), 0) + 1
                pos = None
        for s in ev.get(j, []):
            if pos is not None or j + 1 >= len(m15):
                continue
            nb = m15[j + 1]; NL = lt(nb.t)
            if NL.weekday() >= 5 or not (start <= NL.hour < 22) or per_day.get(NL.date(), 0) >= 4:
                continue
            if maxloss and loss_day.get(NL.date(), 0) >= maxloss:
                continue
            sell = s["side"] == "SELL"
            entry = nb.o + (0 if sell else spread)
            risk = max(abs(s["sl"] - entry), p.min_sl * k)
            if risk > p.max_sl * k or (sell and entry >= s["sl"]) or (not sell and entry <= s["sl"]):
                continue
            pos = dict(side=s["side"], entry=entry, risk=risk, t=nb.t, typ=s["typ"], tf=s["tf"], lv=s["level"],
                       sl=entry + risk if sell else entry - risk,
                       tp=entry - p.rr * risk if sell else entry + p.rr * risk)
            per_day[NL.date()] = per_day.get(NL.date(), 0) + 1
    return T


def stats(T):
    eq = pk = dd = 0
    for x in sorted(T, key=lambda x: x["t"]):
        eq += x["usd"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    w = sum(x["r"] > 0.05 for x in T)
    return f"{len(T):5} tr {sum(x['usd'] for x in T):+7.0f}$ DD {dd:5.0f}$ fit {w / max(len(T), 1):4.0%}"


def htf_of(m5):
    # D1: dita tregtare 17:00-17:00 NY ~ 22:00 UTC (offset 2 ore)
    return {"H4": aggregate(m5, 240), "D1": aggregate(m5, 1440, offset_ms=2 * 3_600_000), "H1": aggregate(m5, 60)}


def evaluate(hist, m26, p, years=range(2016, 2026)):
    a = run(aggregate(m26, 15), htf_of(m26), p=p)
    H = []
    for y in years:
        t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        b5 = [b for b in hist if t0 - 60 * 86400000 <= b.t < t0 + 366 * 86400000]
        k = statistics.median(b.c for b in b5 if b.t >= t0) / 4513.71
        pk = P(**{**p.__dict__, "min_sl": p.min_sl, "max_sl": p.max_sl})
        H += [x for x in run(aggregate(b5, 15), htf_of(b5), k=k, spread=0.2 * k, p=pk) if t0 <= x["t"] < t0 + 365.25 * 86400000]
    return a, H


if __name__ == "__main__":
    hist = pickle.load(open(sys.argv[1], "rb"))
    m26 = pickle.load(open(sys.argv[2], "rb"))
    V = eval(sys.argv[3]) if len(sys.argv) > 3 else {"baza": {}}
    for name, kw in V.items():
        a, H = evaluate(hist, m26, P(**kw))
        print(f"{name:40} | 2026 {stats(a)} | 10v {stats(H)}", flush=True)
