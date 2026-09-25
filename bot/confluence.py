"""Moduli i konfluences: metoda e pronarit si rregull i pergjithshem.

Nje nivel i kohes se larte (H1/H4) + zona FRESH te kohes se ulet ne te njejtin vend
(+ trendline M30) + rejection ne M5 -> hyrje ne mbylljen e qirit, SL pertej wick-ut,
TP te niveli fresh me i afert perballe (zone M15+ ose trendline).

Ne 8 muaj (M5 nga llogaria): me >= 4 nivele te bashkuara 64 trade, +23.3R, fitimprurese ne
te dy periudhat; me 2 nivele humb, me 3 fiton me pak. Si modul i dyte krahas modit sniper:
+173.7R ne vend te +150.3R, drawdown 20.0R ne vend te 21.4R, muaji me i keq +11.4R ne vend te +4.0R.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from .strategy import Bar, adr_series
from .zones import SRV, aggregate, find_zones, swings, with_flips

TF = {"M5": 300_000, "M15": 900_000, "M30": 1_800_000, "H1": 3_600_000, "H4": 14_400_000}
HTF = ("H1", "H4")


@dataclass
class ConfParams:
    disp: float = 1.5            # zona: levizje >= kaq x ATR pas qirit baze
    tfs: tuple = ("M5", "M15", "M30", "H1", "H4")
    min_conf: int = 4            # sa nivele te bashkuara (kohe te ndryshme + trendline)
    need_htf: bool = True        # te pakten njeri nga nivelet duhet te jete H1/H4
    use_tl: bool = True
    tl_tol_adr: float = 0.03
    fresh: bool = True
    zone_age_days: float = 10
    rej_wick: float = 0.5        # rejection: wick >= kaq pjese e qirit M5, mbyllje ne gjysmen tjeter
    sl_buf: float = 0.5
    min_sl: float = 1.0
    max_sl: float = 20.0
    min_rr: float = 3.0          # TP duhet te jete >= kaq R larg


def prepare(m5, p: ConfParams):
    series = {"M5": m5, "M15": aggregate(m5, 15), "M30": aggregate(m5, 30),
              "H1": aggregate(m5, 60), "H4": aggregate(m5, 240, SRV)}
    zones = []
    for tf in p.tfs:
        zones += with_flips(find_zones(series[tf], TF[tf], p.disp, tf=tf), series[tf], TF[tf])
    zones.sort(key=lambda z: z.known)
    return dict(zones=zones, lines=trendlines(series["M30"]), adr=adr_series(m5, 10))


def trendlines(m30):
    """Trendline M30 nga mbylljet: dy swing (low-e rritese ose high-e zbritese), pa mbyllje pertej vijes."""
    line_bars = [Bar(x.t, x.c, x.c, x.c, x.c) for x in m30]
    lines, lows, highs = [], [], []
    for c, i, k, v in swings(line_bars, 2):
        src = lows if k == "L" else highs
        src.append((i, v))
        if len(src) < 2:
            continue
        (i1, v1), (i2, v2) = src[-2], src[-1]
        if i2 - i1 < 6 or not ((k == "L" and v2 > v1) or (k == "H" and v2 < v1)):
            continue
        slope = (v2 - v1) / (i2 - i1)
        if not all((m30[x].c >= v1 + slope * (x - i1) - 1e-9) if k == "L" else
                   (m30[x].c <= v1 + slope * (x - i1) + 1e-9) for x in range(i1, i2 + 1)):
            continue
        dead = m30[i2].t + 144 * TF["M30"]
        for x in range(i2 + 1, min(len(m30), i2 + 145)):
            y = v1 + slope * (x - i1)
            if (k == "L" and m30[x].c < y) or (k == "H" and m30[x].c > y):
                dead = m30[x].t + TF["M30"]
                break
        lines.append(dict(kind="D" if k == "L" else "S", t1=m30[i1].t, v1=v1, slope=slope,
                          known=m30[c].t + TF["M30"], dead=dead))
    return lines


def active_zones(zones, b, p: ConfParams):
    t_close = b.t + TF["M5"]
    age = p.zone_age_days * 86_400_000
    return [z for z in zones if z.known <= t_close and z.dead > b.t and b.t - z.known <= age]


def evaluate(b, adr, active, lines, p: ConfParams):
    """Sinjali ne mbylljen e qirit M5 `b`: dict(side, sl, tp, levels) ose None.
    Hyrja eshte ne mbylljen e qirit (b.c)."""
    rng = b.h - b.l
    if rng <= 0 or adr != adr:
        return None
    t_close = b.t + TF["M5"]
    tl_now = [(L["kind"], L["v1"] + L["slope"] * (b.t - L["t1"]) / TF["M30"]) for L in lines
              if L["known"] <= t_close < L["dead"]] if p.use_tl else []
    tol = p.tl_tol_adr * adr

    def fresh(z):
        return not p.fresh or z.first_touch >= b.t - TF[z.tf] + TF["M5"]

    for side in ("SELL", "BUY"):
        sell = side == "SELL"
        kind = "S" if sell else "D"
        if sell:
            rej = (b.h - max(b.o, b.c)) / rng >= p.rej_wick and b.c < (b.h + b.l) / 2
            ext = b.h
        else:
            rej = (min(b.o, b.c) - b.l) / rng >= p.rej_wick and b.c > (b.h + b.l) / 2
            ext = b.l
        if not rej:
            continue
        tfs_hit = {z.tf for z in active if z.kind == kind and z.lo - 0.5 <= ext <= z.hi + 0.5 and fresh(z)}
        hit_tl = any(k == kind and abs(ext - v) <= tol for k, v in tl_now)
        if len(tfs_hit) + hit_tl < p.min_conf or (p.need_htf and not tfs_hit & set(HTF)):
            continue
        sl = b.h + p.sl_buf if sell else b.l - p.sl_buf
        risk = max(abs(b.c - sl), p.min_sl)
        if risk > p.max_sl:
            continue
        opp = "D" if sell else "S"
        cands = [(z.hi if sell else z.lo) for z in active if z.kind == opp and z.tf != "M5" and fresh(z)]
        cands += [v for k, v in tl_now if k == opp]
        cands = [c for c in cands if (sell and c <= b.c - p.min_rr * risk) or (not sell and c >= b.c + p.min_rr * risk)]
        if not cands:
            continue
        return dict(side=side, sl=sl, tp=max(cands) if sell else min(cands), risk=risk,
                    levels=sorted(tfs_hit) + (["TL"] if hit_tl else []))
    return None


def weekend_or_offhours(t_ms, start_h, end_h, close_friday_utc):
    hr = datetime.fromtimestamp(t_ms / 1000, timezone.utc)
    return not (start_h <= hr.hour < end_h) or (close_friday_utc >= 0 and (
        (hr.weekday() == 4 and hr.hour >= close_friday_utc) or hr.weekday() >= 5))
