"""Zonat supply/demand, zonat e kthyera (flip), swing-et dhe grupimi i qirinjve ne kohe me te medha."""
import bisect
from dataclasses import dataclass

from .strategy import Bar, atr_series

SRV = 3 * 3_600_000  # ora e serverit IC Markets (UTC+3): H4 niset nga 00:00 e serverit


def aggregate(m5, minutes, offset_ms=0):
    """Bashkon qirinjte M5 ne qirinj me te medhenj (p.sh. 15, 30, 60, 240 minuta)."""
    ms = minutes * 60_000
    out, cur, key = [], None, None
    for b in m5:
        k = (b.t + offset_ms) // ms
        if k != key:
            if cur:
                out.append(cur)
            key = k
            cur = Bar(k * ms - offset_ms, b.o, b.h, b.l, b.c)
        else:
            cur = Bar(cur.t, cur.o, max(cur.h, b.h), min(cur.l, b.l), b.c)
    if cur:
        out.append(cur)
    return out


@dataclass
class Zone:
    kind: str                  # "S" supply, "D" demand
    lo: float
    hi: float
    known: int                 # koha (ms) kur zona njihet
    dead: int = 2**62          # koha kur zona prishet (mbyllje pertej saj)
    first_touch: int = 2**62   # prekja e pare pas krijimit: deri atehere zona eshte "fresh"
    tf: str = ""


def _track(z, bars, times, tf_ms):
    """Gjen prekjen e pare dhe prishjen e zones ne qirinjte pas krijimit."""
    for x in bars[bisect.bisect_left(times, z.known - tf_ms + 1):]:
        if x.t + tf_ms <= z.known:
            continue
        if z.first_touch == 2**62 and ((z.kind == "S" and x.h >= z.lo) or (z.kind == "D" and x.l <= z.hi)):
            z.first_touch = x.t
        if (z.kind == "S" and x.c > z.hi) or (z.kind == "D" and x.c < z.lo):
            z.dead = x.t + tf_ms
            break


def find_zones(bars, tf_ms, disp=1.5, look=3, atr_n=14, tf=""):
    """Supply: qiri baze para nje renieje >= disp x ATR brenda `look` qirinjve (demand: pasqyra)."""
    atr = atr_series(bars, atr_n)
    times = [x.t for x in bars]
    zones = []
    for j in range(atr_n, len(bars) - look):
        a = atr[j]
        if a != a:
            continue
        b = bars[j]
        nxt = bars[j + 1:j + 1 + look]
        if min(x.l for x in nxt) <= b.l - disp * a and b.h >= nxt[0].h:
            zones.append(Zone("S", min(b.o, b.c), max(b.h, nxt[0].h), bars[j + look].t + tf_ms, tf=tf))
        if max(x.h for x in nxt) >= b.h + disp * a and b.l <= nxt[0].l:
            zones.append(Zone("D", min(b.l, nxt[0].l), max(b.o, b.c), bars[j + look].t + tf_ms, tf=tf))
    for z in zones:
        _track(z, bars, times, tf_ms)
    return zones


def with_flips(zones, bars, tf_ms):
    """Kur nje zone thyhet, nga ai moment behet zone e kundert (demand e thyer -> supply)."""
    times = [x.t for x in bars]
    out = list(zones)
    for z in zones:
        if z.dead >= 2**62:
            continue
        f = Zone("D" if z.kind == "S" else "S", z.lo, z.hi, z.dead, tf=z.tf)
        _track(f, bars, times, tf_ms)
        out.append(f)
    return out


def swings(bars, k=2):
    """Pikat swing te konfirmuara: (indeksi i konfirmimit, indeksi, 'H'/'L', cmimi)."""
    out = []
    for i in range(k, len(bars) - k):
        h, l = bars[i].h, bars[i].l
        if all(h > bars[i - d].h for d in range(1, k + 1)) and all(h >= bars[i + d].h for d in range(1, k + 1)):
            out.append((i + k, i, "H", h))
        if all(l < bars[i - d].l for d in range(1, k + 1)) and all(l <= bars[i + d].l for d in range(1, k + 1)):
            out.append((i + k, i, "L", l))
    out.sort()
    return out
