"""Snajperi i lajmeve: lajmet e medha te SHBA-se per arin.

Lajmet dalin ne ore fikse te New York-ut: 8:30 (CPI, NFP, PPI, shitjet), 10:00 (ISM, JOLTS),
14:00 (FOMC). Nese qiri M5 qe nis ne ate ore kercen >= 2.5 x ATR(14) me trup >= 50% te qirit,
boti hyn ne drejtim te kercimit ne mbyllje, SL pertej qirit, pastaj break-even dhe trailing.
Ne 8 muaj ari: 25 trade, +24.6R (shk-maj +13.1R, qer-sht +11.5R); kthimi kunder lajmit humbi
ne cdo variant (research/news.py).

Kalendari (ForexFactory, java aktuale) jep emrin e lajmit dhe ndalon hyrjet e sniper-it
30 minuta para lajmeve High USD. Nese kalendari s'arrihet, moduli punon gjithsesi nga oret fikse.
"""
import json
import logging
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from .strategy import atr_series

log = logging.getLogger("gold-sniper")
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
NEWS_TIMES = ((8, 30), (10, 0), (14, 0))       # ora e New York-ut


def ny_offset(d):
    """Sa ore UTC eshte ora e New York-ut (DST: e diela e 2-te e marsit - e diela e 1-re e nentorit)."""
    mar = datetime(d.year, 3, 8, tzinfo=timezone.utc)
    start = mar + timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(d.year, 11, 1, tzinfo=timezone.utc)
    end = nov + timedelta(days=(6 - nov.weekday()) % 7)
    return 4 if start <= d < end else 5


def is_news_time(t_ms):
    d = datetime.fromtimestamp(t_ms / 1000, timezone.utc)
    if d.weekday() >= 5:
        return False
    off = ny_offset(d)
    return any(d.hour == (h + off) % 24 and d.minute == m for h, m in NEWS_TIMES)


def news_signal(m5, k=2.5, sl_buf=0.5):
    """Sinjali ne mbylljen e qirit te fundit M5: dict(side, sl, bar) ose None."""
    if len(m5) < 20:
        return None
    b = m5[-1]
    if not is_news_time(b.t):
        return None
    a = atr_series(m5[:-1], 14)[-1]
    rng = b.h - b.l
    if a != a or rng < k * a or abs(b.c - b.o) < 0.5 * rng:
        return None
    up = b.c > b.o
    return dict(side="BUY" if up else "SELL", sl=(b.l - sl_buf) if up else (b.h + sl_buf), bar=b, atr=a)


class Calendar:
    """Lajmet High USD te javes nga ForexFactory (rifreskim cdo 6 ore; gabimet injorohen)."""

    def __init__(self):
        self.events = []        # (t_ms, titulli)
        self.loaded = 0.0

    def refresh(self):
        if time.time() - self.loaded < 6 * 3600:
            return
        self.loaded = time.time()
        try:
            req = urllib.request.Request(FF_URL, headers={"User-Agent": "gold-sniper"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode())
            ev = []
            for e in data:
                if e.get("country") == "USD" and e.get("impact") == "High":
                    t = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
                    ev.append((int(t.timestamp() * 1000), e.get("title", "")))
            self.events = sorted(ev)
            log.info("Kalendari: %d lajme High USD kete jave", len(ev))
        except Exception as e:
            self.loaded = time.time() - 5 * 3600      # provo perseri pas 1 ore
            log.warning("Kalendari i lajmeve s'u lexua: %s", e)

    def titles_at(self, t_ms, window_ms=5 * 60_000):
        return [n for t, n in self.events if abs(t - t_ms) < window_ms]

    def upcoming(self, now_ms, minutes=30):
        """Lajmi High USD brenda `minutes` minutave te ardhshme (titulli) ose None."""
        for t, n in self.events:
            if 0 <= t - now_ms <= minutes * 60_000:
                return n
        return None
