"""Prototip kerkimi (jo ne botin live): metoda e perdoruesit, versioni shume-kohesh.

BUY (SELL eshte pasqyra):
  H4   mbeshtetje: koka e QM eshte afer nje low-i te meparshem H4 (swing low)
  M30  divergjence AO: price lower low, AO higher low (opsionale)
  M15  Quasimodo: left shoulder (low) -> high ne mes -> koka (lower low) -> mbyllje M15 mbi high-in
  kthim ne zonen QM (deri te left shoulder), lejohet wick nen koke (sweep), anulohet kur
       nje M15 mbyllet nen koke - inv_tol
  M5   rejection (wick i gjate poshte, mbyllje lart) -> hyrje ne mbylljen e qirit
  SL   nen wick-un e rejection-it; TP ne zonen M5 supply qe s'eshte prekur ende
Ekzekuto nga rrenja e repo-s: python -m research.quasimodo_mtf <m5.pkl>
"""
import sys
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.strategy import atr_series, adr_series
from research.quasimodo import aggregate, find_zones, ao_series, swings

SRV = 3 * 3_600_000  # ora e serverit IC Markets (UTC+3): H4 niset nga 00:00 e serverit


def aggregate_srv(m5, minutes):
    """Si aggregate(), por i rreshtuar me oren e serverit (per H4)."""
    from bot.strategy import Bar
    ms = minutes * 60_000
    out, cur, key = [], None, None
    for b in m5:
        k = (b.t + SRV) // ms
        if k != key:
            if cur:
                out.append(cur)
            key = k
            cur = Bar(k * ms - SRV, b.o, b.h, b.l, b.c)
        else:
            cur = Bar(cur.t, cur.o, max(cur.h, b.h), min(cur.l, b.l), b.c)
    if cur:
        out.append(cur)
    return out


@dataclass
class P:
    swing_k: int = 2
    use_h4: bool = True
    h4_band_adr: float = 0.15     # koka duhet te jete kaq x ADR afer nje swing H4
    h4_days: int = 30
    use_ao30: bool = True
    ao_window_h: float = 12       # divergjenca M30 duhet te kete ndodhur brenda kaq oresh para kokes
    expire_m15: int = 48          # sa qirinj M15 pas thyerjes pritet kthimi (12 ore)
    inv_tol_adr: float = 0.05     # anulim kur M15 mbyllet kaq x ADR pertej kokes
    lvl_tol: float = 1.0          # $: kthimi duhet te arrije left shoulder +- kaq
    rej_wick: float = 0.5         # rejection: wick >= kaq pjese e qirit
    sl_buf: float = 0.5
    min_sl: float = 1.0
    max_sl: float = 20.0
    min_rr: float = 1.5
    fallback_rr: float = 0.0
    m5_disp: float = 1.5
    start_h: int = 1
    end_h: int = 20
    spread: float = 0.2


def prepare(m5, p: P):
    m15 = aggregate(m5, 15)
    m30 = aggregate(m5, 30)
    h4 = aggregate_srv(m5, 240)
    return dict(
        m15=m15, m30=m30, h4=h4,
        adr15=adr_series(m15, 10),
        sw15=swings(m15, p.swing_k), sw30=swings(m30, p.swing_k), sw4=swings(h4, p.swing_k),
        ao30=ao_series(m30), zm5=find_zones(m5, 300_000, p.m5_disp),
    )


def run(m5, p: P, ind=None):
    ind = ind or prepare(m5, p)
    m15, m30, h4 = ind["m15"], ind["m30"], ind["h4"]
    adr15 = ind["adr15"]
    # kohet e konfirmimit te swing-eve (ms)
    sw15 = [(m15[c].t + 900_000, i, k, v) for c, i, k, v in ind["sw15"]]
    sw30 = [(m30[c].t + 1_800_000, m30[i].t, k, v, ind["ao30"][i]) for c, i, k, v in ind["sw30"]]
    sw4 = [(h4[c].t + 14_400_000, k, v) for c, i, k, v in ind["sw4"]]
    zm5 = ind["zm5"]
    m15_by_t = {b.t: j for j, b in enumerate(m15)}

    trades, setups, hist15 = [], [], []
    pos = None
    s15 = 0
    for i, b in enumerate(m5):
        t_close = b.t + 300_000
        # ---- pozicioni
        if pos:
            buy = pos["side"] == "BUY"
            lo, hi = (b.l, b.h) if buy else (b.l + p.spread, b.h + p.spread)
            x = None
            if (buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"]):
                x = pos["sl"]
            elif (buy and hi >= pos["tp"]) or (not buy and lo <= pos["tp"]):
                x = pos["tp"]
            if x is not None:
                pos["r"] = ((x - pos["entry"]) if buy else (pos["entry"] - x)) / pos["risk"]
                pos["exit_t"] = b.t
                trades.append(pos)
                pos = None
        # ---- swing-et M15 te konfirmuara deri ne mbylljen e ketij qiri M5
        while s15 < len(sw15) and sw15[s15][0] <= t_close:
            hist15.append(sw15[s15])
            s15 += 1
            new = hist15[-1]
            for side, kind, other in (("BUY", "L", "H"), ("SELL", "H", "L")):
                if new[2] != kind:
                    continue
                same = [s for s in hist15[-8:] if s[2] == kind]
                if len(same) < 2:
                    continue
                head, ls = same[-1], same[-2]
                if (side == "BUY" and head[3] >= ls[3]) or (side == "SELL" and head[3] <= ls[3]):
                    continue
                mids = [s for s in hist15[-8:] if s[2] == other and ls[1] < s[1] < head[1]]
                if not mids:
                    continue
                mid = max(mids, key=lambda s: s[3]) if side == "BUY" else min(mids, key=lambda s: s[3])
                head_t = m15[head[1]].t
                A = adr15[head[1]]
                if A != A:
                    continue
                # H4: koka afer nje swing low/high te meparshem H4
                if p.use_h4:
                    lv = [v for ct, k, v in sw4 if k == kind and ct <= head_t and head_t - ct <= p.h4_days * 86_400_000]
                    if not any(abs(head[3] - v) <= p.h4_band_adr * A for v in lv):
                        continue
                # M30: divergjence AO ne dy swing-et e fundit para kokes
                if p.use_ao30:
                    s30 = [s for s in sw30 if s[2] == kind and s[0] <= head_t + 1_800_000 and
                           head_t - s[1] <= p.ao_window_h * 3_600_000]
                    ok = False
                    if len(s30) >= 2:
                        a, c = s30[-2], s30[-1]
                        if side == "BUY":
                            ok = c[3] < a[3] and c[4] > a[4]
                        else:
                            ok = c[3] > a[3] and c[4] < a[4]
                    if not ok:
                        continue
                setups.append(dict(side=side, head=head[3], lvl=ls[3], brk=mid[3], A=A,
                                   born15=head[1], broken=None))
        # ---- setup-et: thyerja (M15 close), anulimi, kthimi + rejection M5
        j15 = m15_by_t.get(b.t - b.t % 900_000)
        m15_closed = (b.t + 300_000) % 900_000 == 0 and j15 is not None
        keep = []
        for s in setups:
            buy = s["side"] == "BUY"
            if m15_closed:
                c15 = m15[j15].c
                if (buy and c15 < s["head"] - p.inv_tol_adr * s["A"]) or \
                        (not buy and c15 > s["head"] + p.inv_tol_adr * s["A"]):
                    continue
                if s["broken"] is None and ((buy and c15 > s["brk"]) or (not buy and c15 < s["brk"])):
                    s["broken"] = j15
                if s["broken"] is None and j15 - s["born15"] > p.expire_m15:
                    continue
                if s["broken"] is not None and j15 - s["broken"] > p.expire_m15:
                    continue
            if s["broken"] is None or pos is not None:
                keep.append(s)
                continue
            rng = b.h - b.l
            if buy:
                touched = b.l <= s["lvl"] + p.lvl_tol
                rej = rng > 0 and (min(b.o, b.c) - b.l) / rng >= p.rej_wick and b.c > (b.h + b.l) / 2
            else:
                touched = b.h >= s["lvl"] - p.lvl_tol
                rej = rng > 0 and (b.h - max(b.o, b.c)) / rng >= p.rej_wick and b.c < (b.h + b.l) / 2
            if not (touched and rej):
                keep.append(s)
                continue
            hr = datetime.fromtimestamp(t_close / 1000, timezone.utc)
            if not (p.start_h <= hr.hour < p.end_h) or (hr.weekday() == 4 and hr.hour >= 19):
                keep.append(s)
                continue
            entry = b.c + (p.spread if buy else 0)            # hyrje ne mbylljen e qirit
            slp = b.l - p.sl_buf if buy else b.h + p.sl_buf
            risk = max(abs(entry - slp), p.min_sl)
            if risk > p.max_sl:
                keep.append(s)
                continue
            # TP: zona M5 perballe, e njohur dhe e paprekur deri tani
            want = "S" if buy else "D"
            cands = []
            for z in zm5:
                if z.kind != want or z.known > t_close or z.dead <= t_close:
                    continue
                edge = z.lo if buy else z.hi
                if (buy and edge >= entry + p.min_rr * risk) or (not buy and edge <= entry - p.min_rr * risk):
                    cands.append((abs(edge - entry), edge, z))
            tgt = None
            for _, edge, z in sorted(cands, key=lambda c: c[0]):
                touched_after = any((m5[k].h >= z.lo if buy else m5[k].l <= z.hi)
                                    for k in range(max(0, i - 600), i + 1) if m5[k].t >= z.known)
                if not touched_after:  # e pamitiguar
                    tgt = edge
                    break
            if tgt is None and p.fallback_rr > 0:
                tgt = entry + p.fallback_rr * risk if buy else entry - p.fallback_rr * risk
            if tgt is None:
                keep.append(s)
                continue
            pos = dict(side=s["side"], entry=entry, risk=risk, t=t_close,
                       sl=entry - risk if buy else entry + risk, tp=tgt, head=s["head"], lvl=s["lvl"])
        setups = keep
    return trades, sum(t["r"] for t in trades)


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    T, tot = run(m5, P())
    print(len(T), "trade", f"{tot:+.1f}R")

# Rezultati (M5 nga llogaria, 26 jan - 25 sht 2026), P() me te gjitha filtrat (H4 + AO M30):
# 16 trade, 19% fitime, -6.3R (shk-maj -10.0R, qer-sht +3.7R). Pa AO: 207 trade, -18.3R.
# Pa H4 dhe pa AO: 313 trade, -39.2R. Shembulli i perdoruesit (BUY 25 Sep ~17:00 ne 4254) nuk
# kapet: left shoulder qe sheh syri (4268, 07:15) s'eshte swing sipas rregullit k=2, dhe boti
# hyn menjehere pas thyerjes ne vend qe te prese kthimin e vertete.
