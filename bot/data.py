"""Marrja e qirinjve M15 nga cTrader."""
from .mcp_client import PRICE_SCALE
from .strategy import Bar

M15_MS = 15 * 60 * 1000
MAX_RANGE_MS = 719 * 3600 * 1000  # serveri pranon max 720h per thirrje
PAGE_SIZE = 1000


def fetch_bars(client, symbol_id, from_ms, to_ms):
    """Kthen qirinjte M15 te renditur nga me i vjetri, pa dublikata."""
    # Serveri kthen max `count` qirinjte me te fundit te intervalit,
    # prandaj ecim mbrapsht nga `to_ms` deri tek `from_ms`.
    bars = {}
    end = to_ms
    while end > from_ms:
        start = max(from_ms, end - MAX_RANGE_MS)
        res = client.call("get_trendbars", {
            "symbolId": symbol_id, "period": "M_15",
            "fromTimestamp": str(start), "toTimestamp": str(end), "count": PAGE_SIZE,
        })
        chunk = res.get("trendbars", [])
        for tb in chunk:
            bars[tb["timestamp"]] = Bar(
                t=int(tb["timestamp"]),
                o=tb["open"] / PRICE_SCALE,
                h=tb["high"] / PRICE_SCALE,
                l=tb["low"] / PRICE_SCALE,
                c=tb["close"] / PRICE_SCALE,
            )
        if len(chunk) >= PAGE_SIZE:
            end = min(tb["timestamp"] for tb in chunk) - 1
        else:
            end = start
    return [bars[k] for k in sorted(bars)]


def closed_bars(bars, now_ms):
    """Heq qirin qe eshte ende duke u formuar."""
    return [b for b in bars if b.t + M15_MS <= now_ms]
