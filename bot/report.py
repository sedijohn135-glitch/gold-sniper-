"""Raporti javor ne Telegram: e premte 22:50 (XAUUSD) dhe e diel 22:50 (BTCUSD), ora e pronarit.

Trade-t dhe fitimi merren nga deal-et e cTrader-it (te sakta edhe pas nje rinisjeje ne Railway);
moduli dhe R-ja nga ditari i botit (ne memorie, s'ruhen pas rinisjes: atehere shfaqen si "?").
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

MODULE_NAMES = {"main": "Sniper", "conf": "Konfluenca", "hier": "Hierarkia", "news": "Lajmi", "zone": "Zona sniper",
                "old": "Sniper/fiks (pas rinisjes)", "?": "i panjohur (para rinisjes)"}
DAYS = ["Hen", "Mar", "Mer", "Enj", "Pre", "Sht", "Die"]


def local_offset(dt):
    """Ora e pronarit (Europe/Belgrade): CEST +2 nga e diela e fundit e marsit 01:00 UTC
    deri te e diela e fundit e tetorit 01:00 UTC, perndryshe CET +1."""
    def last_sunday(month):
        d = datetime(dt.year, month + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    return 2 if last_sunday(3) <= dt < last_sunday(10) else 1


def local(dt):
    return dt + timedelta(hours=local_offset(dt))


def due(now_utc, sent):
    """Cili raport duhet derguar tani: "gold" te premten, "btc" te dielen, pas ores 22:50."""
    lt = local(now_utc)
    if lt.hour < 22 or (lt.hour == 22 and lt.minute < 50) or lt.hour > 23:
        return None
    kind = {4: "gold", 6: "btc"}.get(lt.weekday())
    if kind and (lt.date(), kind) not in sent:
        return kind
    return None


def price(v):
    """Cmimi here si 4290.5 e here si 429050000 (1/100000)."""
    v = float(v)
    return v / 100000 if v > 1_000_000 else v


def closed_positions(deals, symbol_id, units_scale=100):
    """Pozicionet e mbyllura nga deal-et: (pid, ana, hyrja, dalja, njesite, t_hapje, t_mbyllje, komisioni)."""
    by = defaultdict(list)
    for d in deals:
        if d.get("symbolId") == symbol_id and d.get("dealStatus", "FILLED") == "FILLED":
            by[d.get("positionId")].append(d)
    out = []
    for pid, ds in by.items():
        ds.sort(key=lambda x: x.get("executionTimestamp", 0))
        if len(ds) < 2:
            continue
        o = ds[0]
        # mbyllje te pjesshme: te gjitha deal-et ne anen tjeter; dalja = mesatarja sipas volumit
        cs = [x for x in ds[1:] if x.get("tradeSide") != o.get("tradeSide") and x.get("executionPrice")]
        if not cs:
            continue
        vols = [x.get("filledVolume") or x.get("volume") or 0 for x in cs]
        vol = sum(vols)
        if vol <= 0:
            continue
        exit_px = sum(price(x["executionPrice"]) * v for x, v in zip(cs, vols)) / vol
        out.append(dict(pid=pid, side=o["tradeSide"], entry=price(o["executionPrice"]), exit=exit_px,
                        units=vol / units_scale, opened=o.get("executionTimestamp", 0),
                        closed=cs[-1].get("executionTimestamp", 0),
                        commission=sum(x.get("commission", 0) or 0 for x in ds)))
    return sorted(out, key=lambda x: x["opened"])


def build(bot, market, start_ms, end_ms, open_positions):
    """Teksti i raportit per tregun `market` (Market) mes start_ms dhe end_ms."""
    res = bot.client.call("get_deals", {"fromTimestamp": str(start_ms - 7 * 86_400_000), "toTimestamp": str(end_ms),
                                        "maxRows": 1000})
    trades = [t for t in closed_positions(res.get("deals", []), market.symbol_id) if start_ms <= t["closed"] <= end_ms]
    k = 10 ** bot.money_digits
    rows, per = [], defaultdict(lambda: [0, 0.0, 0.0, 0])
    tot_eur = tot_r = 0.0
    wins = losses = 0
    for t in trades:
        buy = t["side"] == "BUY"
        eur = ((t["exit"] - t["entry"]) if buy else (t["entry"] - t["exit"])) * t["units"] * bot.usd_to_deposit
        eur -= abs(t["commission"]) / k
        j = bot.journal.get(t["pid"], {})
        mod = j.get("module", "?")
        r = j.get("r")
        tot_eur += eur
        wins += eur > 0.5
        losses += eur < -0.5
        p = per[mod]
        p[0] += 1
        p[2] += eur
        if r is not None:
            p[1] += r
            p[3] += 1
            tot_r += r
        dt = local(datetime.fromtimestamp(t["opened"] / 1000, timezone.utc))
        ct = local(datetime.fromtimestamp(t["closed"] / 1000, timezone.utc))
        out = f"{ct:%H:%M}" if ct.date() == dt.date() else f"{DAYS[ct.weekday()]} {ct:%d.%m %H:%M}"
        rows.append(f"{DAYS[dt.weekday()]} {dt:%d.%m} hyrja {dt:%H:%M}, dalja {out} | "
                    f"{t['side']} {t['entry']:.2f}->{t['exit']:.2f} | "
                    f"{MODULE_NAMES.get(mod, mod)} | " + (f"{r:+.1f}R | " if r is not None else "") + f"{eur:+,.2f}")
    s = local(datetime.fromtimestamp(start_ms / 1000, timezone.utc))
    e = local(datetime.fromtimestamp(end_ms / 1000, timezone.utc))
    lines = [f"📒 RAPORTI {market.name} {s:%d.%m}-{e:%d.%m.%Y}",
             f"Trade: {len(trades)} | fitime {wins} | humbje {losses} | BE {len(trades) - wins - losses}",
             f"Rezultati: {tot_r:+.1f}R | {tot_eur:+,.2f} {bot.deposit_asset}"]
    if per:
        lines.append("Sipas modulit:")
        for mod, (n, r, eur, nr) in sorted(per.items(), key=lambda kv: -kv[1][0]):
            lines.append(f"- {MODULE_NAMES.get(mod, mod)}: {n} trade | " + (f"{r:+.1f}R | " if nr else "") +
                         f"{eur:+,.2f} {bot.deposit_asset}")
    if rows:
        lines.append("Trade-t (ora jote):")
        lines += [f"- {x}" for x in rows]
    for q in open_positions:
        lines.append(f"Ende hapur: {q}")
    if bot.last_balance is not None:
        lines.append(f"Balanca: {bot.last_balance:,.2f} {bot.deposit_asset}")
    lines.append("(fitimi nga cmimet e cTrader-it, pa swap)")
    return "\n".join(lines)


def week_start(now_utc, kind):
    """Fillimi i periudhes se raportit ne UTC: e hena 00:00 (ari) ose e shtuna 00:00 (btc), ora jote."""
    lt = local(now_utc)
    back = lt.weekday() if kind == "gold" else lt.weekday() - 5
    start_local = datetime(lt.year, lt.month, lt.day, tzinfo=timezone.utc) - timedelta(days=back)
    return start_local - timedelta(hours=local_offset(now_utc))
