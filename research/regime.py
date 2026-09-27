"""Rezultati i moduleve te botit sipas volatilitetit te arit: ADR e 10 diteve ne % te cmimit.

Ideja: sniper-i dhe hierarkia fituan ne 2026 (ari 4,000-5,000$, ADR 1.8-3% e cmimit) por humbin
ne 10 vitet 2016-2025. Ketu ndahen trade-t e 10 viteve sipas ADR% ne diten e hyrjes.
Ekzekuto nga rrenja e repo-s:
    python -m research.regime <hist_m5.pkl> <m5_2026.pkl>
"""
import pickle
import statistics
import sys
from datetime import datetime, timezone

from research.tenyear import REF, confluence, hierarchy, sniper, year_of


def adr_by_day(m5):
    """ADR e 10 diteve te punes para cdo dite, ne % te mbylljes se dites se meparshme."""
    days = {}
    for b in m5:
        d = b.t // 86_400_000
        h, l, c = days.get(d, (b.h, b.l, b.c))
        days[d] = (max(h, b.h), min(l, b.l), b.c)
    ks = sorted(days)
    out = {}
    for i, d in enumerate(ks):
        prev = [days[x] for x in ks[max(0, i - 10):i] if (x + 3) % 7 < 5]
        if len(prev) >= 5:
            out[d] = statistics.mean(h - l for h, l, c in prev) / days[ks[i - 1]][2] * 100
    return out


if __name__ == "__main__":
    hist = pickle.load(open(sys.argv[1], "rb"))
    m26 = pickle.load(open(sys.argv[2], "rb"))
    rows = []
    for y in list(range(2016, 2026)) + [2026]:
        if y < 2026:
            t0 = datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
            b5 = [b for b in hist if t0 - 40 * 86_400_000 <= b.t and year_of(b.t) <= y]
            k = statistics.median(b.c for b in b5 if b.t >= t0) / REF
        else:
            b5, k, t0 = m26, 1.0, 0
        A = adr_by_day(b5)
        for mod, T in (("sniper", sniper(b5, k, 0.2 * k)), ("hier", hierarchy(b5, k, 0.2 * k)[0]),
                       ("conf", confluence(b5, k, 0.2 * k)[0])):
            rows += [(y, mod, A.get(x["t"] // 86_400_000), x["r"]) for x in T
                     if x["t"] >= t0 and (y == 2026 or year_of(x["t"]) == y)]
    for mod in ("sniper", "hier", "conf"):
        for lo, hi in ((0, 1.6), (1.6, 99), (1.8, 99), (2.0, 99)):
            line = f"{mod:6} ADR {lo}-{hi}% |"
            for per, ys in (("2016-20", range(2016, 2021)), ("2021-25", range(2021, 2026)), ("2026", (2026,))):
                R = [r for y, m, a, r in rows if m == mod and y in ys and a is not None and lo <= a < hi]
                line += f" {per}: {len(R):4} tr {sum(R):+7.1f}R ({sum(R) / max(len(R), 1):+.3f}) |"
            print(line)

# Rezultati (spread 0.20$, R ne total; ne kllapa R per trade):
#                 ADR < 1.6%           ADR >= 1.6%: 2016-20       2021-25        2026 (8 muaj)
#   sniper   7065 tr -401.8R            647 tr +24.8R (+0.04)   839 tr  +2.1R   471 tr +150.3R (+0.32)
#   hier     2666 tr -222.6R            269 tr +37.0R (+0.14)   433 tr +41.5R   337 tr +122.1R (+0.36)
#   conf     1097 tr  -61.3R            109 tr +40.4R (+0.37)    97 tr +15.9R    64 tr  +23.3R (+0.36)
#   Pragjet fqinje 1.8% dhe 2.0% japin te njejten pamje (hier: +52/+39/+123R dhe +25/+44/+123R).
#   Sniper-i me ADR >= 1.8-2.0% del afer zeros ose negativ para 2026: filtri s'e ben fitimprures,
#   vetem e ndal ne periudhat e qeta ku ka humbur ~400R.
#   Perfundimi: modulet fitojne vetem kur ari leviz shume. Boti live s'hap trade me sniper,
#   konfluence e hierarki kur ADR < 1.6% e cmimit (MIN_ADR_PCT). Ne 2026 ADR ishte gjithmone
#   >= 1.76%, pra filtri s'ndryshon asgje sot; e ndal botin kur ari qetesohet.
#   Pragu 1.6% u zgjodh pasi u pane rezultatet sipas ADR-se (jo i parregjistruar).
