"""Backtest: tre modulet e botit ne BTCUSD vetem te shtunen dhe te dielen.

Vlerat ne $ te arit (SL min/max, spread, tolerancat e zonave) shumezohen me k, sepse BTC
leviz ~15-25 here me shume ne dite. Hyrje: e shtune 00:00 - e diel 21:00 UTC; pozicionet
mbyllen te dielen 21:00 UTC. Spread 5$ (IC Markets, shtator 2026).
Ekzekuto nga rrenja e repo-s: python -m research.btc_weekend <btc_m5.pkl>
"""
import contextlib
import dataclasses
import io
import pickle
import sys
from datetime import datetime, timezone

from backtest import run as sniper_run
from bot import confluence as CF, hierarchy as H
from bot.config import Config
from bot.markets import Market
from bot.zones import aggregate
from research.hierarchy import outcome

SPREAD = 5.0
BTC = Market("BTCUSD", 10026, 1, 20.0, 0.25, 1.0, "btc")
HALF = datetime(2026, 5, 28, tzinfo=timezone.utc).timestamp() * 1000


def closed(t_ms):
    return BTC.must_close(datetime.fromtimestamp(t_ms / 1000, timezone.utc))


class BtcCfg(Config):
    def weekend_close(self, when):
        return BTC.must_close(when)

    def in_session(self, hour):
        return True


def sniper(b15, k):
    base = Config.from_env()
    cfg = BtcCfg(**{f.name: getattr(base, f.name) for f in dataclasses.fields(Config)})
    cfg.min_sl, cfg.max_sl, cfg.backtest_spread = base.min_sl * k, base.max_sl * k, SPREAD
    with contextlib.redirect_stdout(io.StringIO()):
        T, _ = sniper_run(b15, cfg, verbose=False)
    return T


def hierarchy(b5, k):
    p = H.scaled(H.P(), k)
    T, free = [], -1
    for c in H.candidates(b5, p, H.prepare(b5, p)):
        if c["i"] <= free or closed(c["t"]):
            continue
        g = H.pick(c, p)
        if not g:
            continue
        r, j = outcome(b5, c, g[1], min_sl=p.min_sl, spread=SPREAD, closed=closed)
        T.append(dict(t=c["t"], r=r))
        free = j
    return T


def confluence(b5, k):
    p = CF.scaled(CF.ConfParams(), k)
    ind = CF.prepare(b5, p)
    zones, lines, adr = ind["zones"], ind["lines"], ind["adr"]
    age = p.zone_age_days * 86_400_000
    T, pos, zi, active = [], None, 0, []
    for i, b in enumerate(b5):
        t_close = b.t + CF.TF["M5"]
        if pos:
            buy = pos["side"] == "BUY"
            lo, hi = (b.l, b.h) if buy else (b.l + SPREAD, b.h + SPREAD)
            x = pos["sl"] if ((buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"])) else \
                pos["tp"] if ((buy and hi >= pos["tp"]) or (not buy and lo <= pos["tp"])) else None
            if x is None and closed(b.t):
                x = b.o + (0 if buy else SPREAD)
            if x is not None:
                pos["r"] = ((x - pos["entry"]) if buy else (pos["entry"] - x)) / pos["risk"]
                T.append(pos)
                pos = None
        while zi < len(zones) and zones[zi].known <= t_close:
            active.append(zones[zi])
            zi += 1
        active = [z for z in active if z.dead > b.t and b.t - z.known <= age]
        if pos is not None or closed(t_close):
            continue
        sig = CF.evaluate(b, adr[i], active, lines, p)
        if not sig:
            continue
        buy = sig["side"] == "BUY"
        entry = b.c + (SPREAD if buy else 0)
        risk = max(abs(entry - sig["sl"]), p.min_sl)
        pos = dict(side=sig["side"], entry=entry, risk=risk, t=t_close,
                   sl=entry - risk if buy else entry + risk, tp=sig["tp"])
    return T


def line(T, name):
    tot = sum(x["r"] for x in T)
    A = sum(x["r"] for x in T if x["t"] < HALF)
    return f"{name:22} {len(T):4} trade {tot:+6.1f}R | shk-maj {A:+6.1f}R qer-sht {tot - A:+6.1f}R"


if __name__ == "__main__":
    b5 = pickle.load(open(sys.argv[1], "rb"))
    b15 = aggregate(b5, 15)
    for k in (10, 15, 20):
        print(line(sniper(b15, k), f"sniper k={k}"))
        print(line(hierarchy(b5, k), f"hierarkia k={k}"))
        print(line(confluence(b5, k), f"konfluenca k={k}"))

# Rezultati (BTCUSD M5 nga llogaria, 26 jan - 26 sht 2026, vetem sht-die):
#   sniper     k=10 149 trade -14.4R | k=15 164 trade +3.2R | k=20 169 trade +17.1R (qer-sht -3.8R)
#   hierarkia  k=10  53 trade  -6.8R | k=15  53 trade +2.5R | k=20  49 trade  +6.5R (qer-sht -4.0R)
#   konfluenca k=10  27 trade  +3.7R | k=15  33 trade +3.9R | k=20  37 trade  +3.6R (qer-sht -7.2R)
#   Qershor-shtator negativ ne cdo variant; vetem ~1 ne 3 fundjava ne fitim. Pa avantazh te qarte:
#   boti live e tregton BTC-ne ne fundjave me rrezik 0.25% (gjysma e arit), k = 20.
