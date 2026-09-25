"""Konfigurimi nga variablat e mjedisit (Railway -> Variables)."""
import os
from dataclasses import dataclass, field

from .strategy import Params


def _env(names, default=None):
    for n in names if isinstance(names, (list, tuple)) else [names]:
        v = os.environ.get(n)
        if v not in (None, ""):
            return v
    return default


def _f(name, default):
    return float(_env(name, default))


def _i(name, default):
    return int(float(_env(name, default)))


def _b(name, default):
    return str(_env(name, str(default))).strip().lower() in ("1", "true", "yes", "po", "on")


@dataclass
class Config:
    url: str = "https://mcp.ctrader.com/trading/mcp"
    bearer: str = ""
    symbol_name: str = "XAUUSD"   # boti tregton VETEM XAUUSD
    symbol_id: int = 41           # XAUUSD tek IC Markets (verifikohet ne start)
    lot_size: int = 100           # 1 lot ari = 100 oz -> volume = lote * 10_000

    dry_run: bool = False
    label: str = "GoldSniper"
    risk_percent: float = 0.5
    fixed_lots: float = 0.0       # >0 -> perdor lot fiks ne vend te % rrezikut
    max_lots: float = 1.0
    min_lots: float = 0.01
    rr: float = 3.0
    break_even_r: float = 1.0
    trail_adr: float = 0.4        # trailing stop: distanca x ADR (0 = TP fiks me RR)
    trail_start_r: float = 1.0    # trailing fillon pasi fitimi arrin kaq R
    rot_tp_adr: float = 0.3       # TP ne ditet e rotacionit (x ADR)
    max_positions: int = 1        # >1: pozicion shtese vetem kur te hapurit jane pa rrezik (SL >= hyrja)
    max_daily_loss_pct: float = 3.0
    max_trades_per_day: int = 4
    min_sl: float = 3.0           # $ cmim
    max_sl: float = 25.0          # $ cmim
    start_hour_utc: int = 1
    end_hour_utc: int = 20
    max_spread: float = 0.5       # $ cmim
    cooldown_bars: int = 4
    poll_seconds: int = 15
    backtest_spread: float = 0.2
    strategy: Params = field(default_factory=Params)

    @property
    def trailing(self) -> bool:
        return self.trail_adr > 0 and self.strategy.mode == "sniper"

    def in_session(self, hour: int) -> bool:
        if self.start_hour_utc <= self.end_hour_utc:
            return self.start_hour_utc <= hour < self.end_hour_utc
        return hour >= self.start_hour_utc or hour < self.end_hour_utc

    @classmethod
    def from_env(cls):
        # MODE=sniper (fillestar): majat/fundet e lekundjeve te dites (ADR)
        # MODE=klasik: modeli i vjeter me lookback + RSI
        mode = str(_env("MODE", "sniper")).strip().lower()
        if mode not in ("sniper", "klasik"):
            raise SystemExit(f"MODE i panjohur: {mode} (perdor 'sniper' ose 'klasik')")
        p = Params(
            lookback=_i("LOOKBACK", 32),
            min_leg_atr=_f("MIN_LEG_ATR", 3.0),
            min_wick_pct=_f("MIN_WICK_PCT", 40),
            min_close_pct=_f("MIN_CLOSE_PCT", 50),
            use_rsi=_b("USE_RSI", True),
            rsi_period=_i("RSI_PERIOD", 14),
            rsi_ob=_f("RSI_OVERBOUGHT", 65),
            rsi_os=_f("RSI_OVERSOLD", 35),
            atr_period=_i("ATR_PERIOD", 14),
            sl_buffer_atr=_f("SL_BUFFER_ATR", 0.3),
            strong_close_pct=_f("STRONG_CLOSE_PCT", 75),
            equal_tol_atr=_f("EQUAL_TOL_ATR", 0),
            mode=mode,
            adr_days=_i("ADR_DAYS", 10),
            swing_rev=_f("SWING_REV", 0.4),
            leg_min_adr=_f("LEG_MIN_ADR", 0.45),
            confirm_bars=_i("CONFIRM_BARS", 2),
            trend_entries=_b("TREND_ENTRIES", True),
            pull_min_adr=_f("PULL_MIN_ADR", 0.10),
            pull_max_adr=_f("PULL_MAX_ADR", 0.35),
            early_trend_adr=_f("EARLY_TREND_ADR", 0.4),
            trend_day_adr=_f("TREND_DAY_ADR", 0.5),
            rot_day_adr=_f("ROT_DAY_ADR", 0.2),
        )
        cfg = cls(
            url=_env(["CTRADER_MCP_URL", "URL"], cls.url),
            bearer=_env(["CTRADER_BEARER", "Bearer", "BEARER"], ""),
            symbol_id=_i("SYMBOL_ID", 41),
            dry_run=_b("DRY_RUN", False),
            label=_env("LABEL", "GoldSniper"),
            risk_percent=_f("RISK_PERCENT", 0.5),
            fixed_lots=_f("FIXED_LOTS", 0),
            max_lots=_f("MAX_LOTS", 1.0),
            rr=_f("RR", 3.0),
            break_even_r=_f("BREAK_EVEN_R", 1.0),
            trail_adr=_f("TRAIL_ADR", 0.4),
            trail_start_r=_f("TRAIL_START_R", 1.0),
            rot_tp_adr=_f("ROT_TP_ADR", 0.3),
            max_positions=_i("MAX_POSITIONS", 1),
            max_daily_loss_pct=_f("MAX_DAILY_LOSS_PCT", 3.0),
            max_trades_per_day=_i("MAX_TRADES_PER_DAY", 4),
            min_sl=_f("MIN_SL", 3.0),
            max_sl=_f("MAX_SL", 25.0),
            start_hour_utc=_i("START_HOUR_UTC", 1),
            end_hour_utc=_i("END_HOUR_UTC", 20),
            max_spread=_f("MAX_SPREAD", 0.5),
            cooldown_bars=_i("COOLDOWN_BARS", 4),
            poll_seconds=_i("POLL_SECONDS", 15),
            strategy=p,
        )
        if not cfg.bearer:
            raise SystemExit("Mungon variabla 'Bearer' (tokeni i cTrader MCP). Shtoje ne Railway -> Variables.")
        return cfg
