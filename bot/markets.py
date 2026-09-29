"""Tregjet e botit: XAUUSD nga e hena ne te premten, BTCUSD te shtunen dhe te dielen.

Cdo treg ka orarin e vet (kur hapen trade, kur mbyllen pozicionet), madhesine e lotit
dhe shkallen e vlerave ne $: strategjite jane ndertuar per arin, prandaj per BTC
SL minimal, spread-i, tolerancat e zonave etj. shumezohen me `scale`.
"""
from dataclasses import dataclass

from .report import local


@dataclass
class Market:
    name: str
    symbol_id: int
    lot_size: int                # 1 lot = lot_size njesi baze (ari 100 oz, kripto 1 BTC)
    scale: float                 # vlerat ne $ te arit x scale
    risk_percent: float
    max_lots: float
    kind: str                    # "gold" ose "btc"
    start_h: int = 1             # ari: orari i hyrjeve (UTC)
    end_h: int = 20
    close_friday_utc: int = 19   # ari: e premte mbremje mbyllet gjithcka
    close_sunday_utc: int = 20   # btc: e diel mbremje mbyllet gjithcka (IC Markets ndal BTC ~21:00 UTC)
    daily_close: str = ""        # ari: "HH:MM" UTC -> cdo dite mbyllet gjithcka (para swap-it); "" = joaktiv
    friday_close_local: str = "" # ari: "HH:MM" ora e pronarit (CET/CEST) te premten; "" = close_friday_utc

    def in_window(self, dt) -> bool:
        """A eshte ky tregu i botit ne kete kohe (pa marre parasysh oret e hyrjes)."""
        wd = dt.weekday()
        if self.kind == "btc":
            return wd == 5 or (wd == 6 and dt.hour < self.close_sunday_utc)
        return not self.must_close(dt)

    def must_close(self, dt) -> bool:
        """Pozicionet e ketij tregu duhet te mbyllen (dhe s'hapen te reja)."""
        wd = dt.weekday()
        if self.kind == "btc":
            return wd < 5 or (wd == 6 and dt.hour >= self.close_sunday_utc)
        if self.daily_close:
            hh, mm = (int(x) for x in self.daily_close.split(":"))
            if (dt.hour, dt.minute) >= (hh, mm) and dt.hour >= self.end_h:
                return True
        if self.friday_close_local:
            hh, mm = (int(x) for x in self.friday_close_local.split(":"))
            lt = local(dt)
            return (lt.weekday() == 4 and (lt.hour, lt.minute) >= (hh, mm)) or (wd >= 5 and lt.weekday() != 0)
        if self.close_friday_utc < 0:
            return False
        return (wd == 4 and dt.hour >= self.close_friday_utc) or wd >= 5

    def can_open(self, dt) -> bool:
        if self.must_close(dt):
            return False
        if self.kind == "btc":
            return True
        if self.start_h <= self.end_h:
            return self.start_h <= dt.hour < self.end_h
        return dt.hour >= self.start_h or dt.hour < self.end_h
