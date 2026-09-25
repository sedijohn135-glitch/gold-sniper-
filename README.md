# Gold Sniper – bot për XAUUSD M15 (Railway + cTrader)

Bot që gjen **majat** dhe **fundet** në XAUUSD M15 (si zonat roze në screenshot)
dhe hap trade automatikisht në llogarinë tënde cTrader.

- Tregton **vetëm XAUUSD** dhe **vetëm M15**.
- Lidhet me cTrader përmes serverit zyrtar **cTrader Trading MCP**
  (`https://mcp.ctrader.com/trading/mcp`) me tokenin tënd `Bearer`.
- Punon 24/7 në **Railway**. Nuk të duhet kompjuter dhe as ta hedhësh botin në cTrader.
  cTrader në telefon e përdor vetëm për të parë trade-t.

## Si funksionon strategjia

| | SELL (majë) | BUY (fund) |
|---|---|---|
| 1 | Qiriu bën high më të lartë se 32 qirinjtë e mëparshëm (8 orë) | Qiriu bën low më të ulët se 32 qirinjtë e mëparshëm |
| 2 | Para kësaj ka pasur ngritje të madhe (≥ 3 × ATR) | Para kësaj ka pasur rënie të madhe (≥ 3 × ATR) |
| 3 | RSI ≥ 65 (mbiblerje) | RSI ≤ 35 (mbishitje) |
| 4 | Refuzim: bisht i gjatë lart (≥40%) dhe mbyllje poshtë, **ose** qiri i fortë bearish që mbyllet në 25% e poshtme, **ose** qiriu tjetër mbyllet nën trupin e majës | Refuzim: bisht i gjatë poshtë dhe mbyllje lart, **ose** qiri i fortë bullish që mbyllet në 25% e sipërme, **ose** qiriu tjetër mbyllet mbi trupin e fundit |

- **SL**: pak mbi majë / nën fund (+0.3 × ATR). Min 3$, max 25$ (nëse del më i madh, trade-i anulohet).
- **TP**: 3 × SL (Risk:Reward 1:3).
- **Break-even**: kur fitimi arrin 1 × SL, SL-ja zhvendoset në hyrje.
- Vetëm 1 pozicion njëherësh, max 4 trade në ditë, stop nëse humbja ditore arrin 3%.
- Tregton 01:00–20:00 UTC (= 04:00–23:00 në orën e grafikut IC Markets).

### Rezultati në 120 ditët e fundit (të dhëna reale M15 nga llogaria jote)

```
Trade: 211 | Fitime: 43 (+3R) | Break-even: 66 | Humbje: 102 (-1R) | Totali: +28.4R
Drawdown max: ~12R | Mesatarisht 2.4 trade në ditë
```

Me 0.5% rrezik për trade, kjo është rreth +14% dhe drawdown max rreth 6%.

### Sa trade në ditë? Modi `sniper` ose `aktiv`

| | `MODE=sniper` (fillestar) | `MODE=aktiv` |
|---|---|---|
| Filtri RSI | 65 / 35 | 60 / 40 |
| Trade në ditë (mesatarisht) | 2.4 | 3.0 |
| Ditë me ≥ 2 trade | 70% | 86% |
| Ditë pa asnjë trade (nga 87) | 8 | 2 |
| Totali në 120 ditë | **+28.4R** | +14.8R |
| 60 ditët e para / 60 të fundit | +11.7R / +15.7R | **−4.1R** / +18.9R |

Më shumë trade = fitim më i vogël: sinjalet shtesë janë më të dobëta.
Provova edhe pa RSI dhe me konfirmim deri në 3 qirinj: 3.5 trade/ditë, por vetëm +3R deri +4R
në 120 ditë dhe humbje në 60 ditët e para. Prandaj fillestari mbetet `sniper`.

Nga 27 majat/fundet e shënuara në screenshot (10–25 shtator), boti i zbulon 16.
Ato që nuk i kap janë kryesisht: fund/majë më e lartë ose më e ulët se e mëparshmja (jo fshirje likuiditeti),
RSI jo aq ekstrem (p.sh. 39 në vend të ≤ 35), ose kthim që vjen 2–3 qirinj më vonë.
Disa të tjera i zbulon, por nuk hap trade sepse ka tashmë pozicion të hapur në të njëjtin drejtim,
është jashtë orarit (00:00 UTC) ose SL-ja del mbi 25$.
Shumica e trade-ve humbin ose dalin në break-even; fitimi vjen nga pak trade të mëdha.
**Rezultatet e kaluara nuk garantojnë rezultatet e ardhshme.** Provoje fillimisht në llogari demo.

Backtest-in mund ta rilidhësh vetë: `python backtest.py 120`

## Vendosja në Railway (nga telefoni)

1. Hap **railway.com** → *Login with GitHub*.
2. **New Project** → **Deploy from GitHub repo** → zgjidh `gold-sniper-`.
3. Te shërbimi → **Variables** → shto:

   | Variabla | Vlera |
   |---|---|
   | `URL` | `https://mcp.ctrader.com/trading/mcp` |
   | `Bearer` | tokeni yt i cTrader MCP (i njëjti që ke tani) |

4. Railway e ndërton vetë me `Dockerfile` dhe e nis botin. Te **Deployments → View logs** duhet të shohësh:
   ```
   XAUUSD symbolId=41 | Valuta e llogarise: EUR | ...
   Boti filloi. Qiri i fundit i mbyllur: ...
   ```
5. (Opsionale) Faqja e statusit: **Settings → Networking → Generate Domain**, pastaj hape linkun në telefon.
   Aty sheh sinjalin e fundit, trade-t e sotme dhe log-et.

> ⚠️ Mbaje **1 replikë** (është vendosur në `railway.json`). Dy kopje të botit do hapnin trade të dyfishta.
>
> ⚠️ Tokeni `Bearer` jep akses tregtimi në llogarinë tënde. Mos e shkruaj kurrë në kod ose në GitHub, vetëm te Railway → Variables.

### Trade-i i parë

Kodi nuk është provuar ende me një urdhër të vërtetë. Kur boti hap trade-in e parë, shiko log-et:

- `U HAP pozicioni ... -> SL ... | TP ...` dhe `SL/TP u vendosen ...` → gjithçka në rregull.
- Nëse SL-ja nuk mund të vendoset, boti e **mbyll menjëherë** pozicionin për siguri dhe e shkruan në log.

Kontrollo edhe në aplikacionin cTrader që pozicioni ka SL dhe TP.
Nëse do ta provosh pa hapur trade, vendos `DRY_RUN=true`: boti shkruan sinjalet në log, por nuk dërgon urdhra.

## Të gjitha parametrat (Railway → Variables)

| Variabla | Vlera fillestare | Çfarë bën |
|---|---|---|
| `MODE` | `sniper` | `aktiv` = më shumë trade (RSI 60/40), fitim më i vogël në backtest |
| `DRY_RUN` | `false` | `true` = vetëm sinjale në log, pa trade |
| `RISK_PERCENT` | `0.5` | % e balancës që rrezikohet për trade |
| `FIXED_LOTS` | `0` | nëse > 0, përdor gjithmonë këtë lot (p.sh. `0.05`) |
| `MAX_LOTS` | `1.0` | loti maksimal për trade (mbrojtje) |
| `RR` | `3.0` | TP = SL × RR |
| `BREAK_EVEN_R` | `1.0` | SL në hyrje pas kaq R fitim (`0` = joaktiv) |
| `MAX_DAILY_LOSS_PCT` | `3.0` | stop për sot pas kaq % humbje |
| `MAX_TRADES_PER_DAY` | `4` | trade maksimale në ditë |
| `MIN_SL` / `MAX_SL` | `3` / `25` | kufijtë e SL në $ |
| `START_HOUR_UTC` / `END_HOUR_UTC` | `1` / `20` | orari i tregtimit (UTC) |
| `MAX_SPREAD` | `0.5` | spread maksimal në $ |
| `LOOKBACK` | `32` | sa qirinj për majë/fund |
| `MIN_LEG_ATR` | `3.0` | lëvizja minimale para majës/fundit (× ATR) |
| `MIN_WICK_PCT` | `40` | bishti minimal i qirit të refuzimit (%) |
| `RSI_OVERBOUGHT` / `RSI_OVERSOLD` | `65` / `35` | filtri RSI |
| `USE_RSI` | `true` | çaktivizo filtrin RSI me `false` |
| `STRONG_CLOSE_PCT` | `75` | qiri i fortë kthimi pa bisht (`0` = joaktiv) |
| `EQUAL_TOL_ATR` | `0` | lejon majë/fund të dyfishtë (p.sh. `0.2`); në backtest ul fitimin |

Llogaria jote demo ka balancë shumë të madhe, prandaj me 0.5% rrezik loti del gjithmonë
te kufiri `MAX_LOTS`. Rregulloje `MAX_LOTS` ose përdor `FIXED_LOTS` sipas dëshirës.

## Struktura

```
bot/main.py        boti live (cikli, urdhrat, break-even, limiti ditor, faqja e statusit)
bot/strategy.py    zbulimi i majave/fundeve
bot/mcp_client.py  lidhja me cTrader Trading MCP
bot/data.py        marrja e qirinjve M15
bot/config.py      parametrat nga variablat e mjedisit
backtest.py        backtest me të dhënat reale
cbot/GoldSniper.cs e njëjta strategji si cBot për cTrader Desktop (opsionale, nëse ke kompjuter)
```
