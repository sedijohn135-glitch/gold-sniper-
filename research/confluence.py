"""Backtest i modulit te konfluences (bot/confluence.py) mbi qirinj M5.

Perdor te njejtin kod sinjali si boti live (bot.confluence.evaluate).
Ekzekuto nga rrenja e repo-s: python -m research.confluence <m5.pkl>
"""
import sys
import pickle
from datetime import datetime, timezone

from bot.confluence import TF, ConfParams, prepare, evaluate, weekend_or_offhours

SPREAD = 0.2


def run(m5, p: ConfParams, ind=None, start_h=1, end_h=20, close_friday_utc=19):
    ind = ind or prepare(m5, p)
    zones, lines, adr = ind["zones"], ind["lines"], ind["adr"]
    age = p.zone_age_days * 86_400_000
    trades, pos = [], None
    zi, active = 0, []
    for i, b in enumerate(m5):
        t_close = b.t + TF["M5"]
        if pos:
            buy = pos["side"] == "BUY"
            lo, hi = (b.l, b.h) if buy else (b.l + SPREAD, b.h + SPREAD)
            x = pos["sl"] if ((buy and lo <= pos["sl"]) or (not buy and hi >= pos["sl"])) else \
                pos["tp"] if ((buy and hi >= pos["tp"]) or (not buy and lo <= pos["tp"])) else None
            if x is None and close_friday_utc >= 0:
                d = datetime.fromtimestamp(b.t / 1000, timezone.utc)
                if (d.weekday() == 4 and d.hour >= close_friday_utc) or d.weekday() >= 5:
                    x = b.o
            if x is not None:
                pos["r"] = ((x - pos["entry"]) if buy else (pos["entry"] - x)) / pos["risk"]
                pos["exit_t"] = b.t
                trades.append(pos)
                pos = None
        while zi < len(zones) and zones[zi].known <= t_close:
            active.append(zones[zi])
            zi += 1
        active = [z for z in active if z.dead > b.t and b.t - z.known <= age]
        if pos is not None or weekend_or_offhours(t_close, start_h, end_h, close_friday_utc):
            continue
        sig = evaluate(b, adr[i], active, lines, p)
        if not sig:
            continue
        buy = sig["side"] == "BUY"
        entry = b.c + (SPREAD if buy else 0)
        risk = max(abs(entry - sig["sl"]), p.min_sl)
        pos = dict(side=sig["side"], entry=entry, risk=risk, t=t_close,
                   sl=entry - risk if buy else entry + risk, tp=sig["tp"], conf=sig["levels"])
    return trades, sum(t["r"] for t in trades)


if __name__ == "__main__":
    m5 = pickle.load(open(sys.argv[1], "rb"))
    T, tot = run(m5, ConfParams())
    print(len(T), "trade", f"{tot:+.1f}R")

# Rezultati (M5 nga llogaria, 26 jan - 25 sht 2026), fresh, rejection 0.5, TP >= 3R:
#   >= 2 nivele: 319 trade, -9.6R | >= 3: 161 trade, +19.8R | >= 4: 64 trade, +23.3R
#   (shk-maj +13.7R, qer-sht +9.6R). Pa zona fresh rezultatet jane me te dobeta.
#   Krahas modit sniper (pozicion i vecante): 535 trade, +173.7R, DD 20.0R, 8/8 muaj ne fitim
#   (muaji me i keq +11.4R). Vete moduli ka muaj me humbje (mars -5.0R, prill -4.0R).
