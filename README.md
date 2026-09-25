# Gold Sniper – bot për XAUUSD M15 (Railway + cTrader)

Bot që gjen **majat** dhe **fundet** në XAUUSD M15 (si zonat roze në screenshot)
dhe hap trade automatikisht në llogarinë tënde cTrader.

- Tregton **vetëm XAUUSD** dhe **vetëm M15**.
- Lidhet me cTrader përmes serverit zyrtar **cTrader Trading MCP**
  (`https://mcp.ctrader.com/trading/mcp`) me tokenin tënd `Bearer`.
- Punon 24/7 në **Railway**. Nuk të duhet kompjuter dhe as ta hedhësh botin në cTrader.
  cTrader në telefon e përdor vetëm për të parë trade-t.

## Si funksionon strategjia (MODE=sniper)

Çdo ditë ari bën 2–3 maja/funde në M15. Boti i mat me aritmetikën e ditës:

- **ADR** = mesatarja e lëvizjes ditore (high − low) të 10 ditëve të fundit. Tani ≈ 90–110$.
- Në 27 majat/fundet që shënove (10–25 shtator), lëvizja nga një majë te fundi tjetër
  ishte pothuajse gjithmonë **≥ 0.45 × ADR (~45$)**, mesatarisht ~0.6 × ADR.
  18 nga 27 ishin high-i ose low-i i ditës.

Rregullat:

| | SELL (majë) | BUY (fund) |
|---|---|---|
| 1 | Boti ndjek lëkundjet e ditës: një fund konfirmohet kur çmimi ngrihet 0.4 × ADR prej tij | Një majë konfirmohet kur çmimi bie 0.4 × ADR prej saj |
| 2 | Çmimi është ngritur **≥ 0.45 × ADR** nga fundi i fundit dhe bën high të ri të kësaj lëvizjeje | Çmimi ka rënë **≥ 0.45 × ADR** nga maja e fundit dhe bën low të ri |
| 3 | Refuzim: bisht i gjatë lart (≥40%), **ose** qiri i fortë bearish që mbyllet në 25% e poshtme, **ose** një nga 2 qirinjtë pas majës mbyllet nën trupin e saj | Refuzim: bisht i gjatë poshtë, **ose** qiri i fortë bullish, **ose** një nga 2 qirinjtë pas fundit mbyllet mbi trupin e tij |

**Dy lloje ditësh.** Ari bën çdo ditë njërën nga dy gjërat: ose trend gjithë ditën (vetëm BUY ose vetëm
SELL), ose rotacion (BUY-SELL-BUY-SELL). Në 81 ditë: 36% trend, 64% rotacion. Boti e përcakton tipin
pas 8 orëve të para të ditës (00:00–08:00 ora e grafikut):

| Kushti | Tipi | Çfarë bën boti |
|---|---|---|
| 8 orët e para lëvizin ≥ 0.4 × ADR, **ose** në çdo moment çmimi është ≥ 0.5 × ADR larg hapjes së ditës | **DITË TRENDI** | vetëm trade në drejtimin e ditës, dalje me trailing |
| 8 orët e para lëvizin < 0.2 × ADR (dhe dita s'është bërë trend) | **DITË ROTACIONI** (81% nuk bëjnë trend) | BUY dhe SELL, TP i vogël 0.3 × ADR (~30$) |
| asnjëra | e paqartë | të dyja drejtimet, dalje me trailing |

Rregulli "në çdo moment" e kap ditën e trendit edhe kur ai fillon vonë ose kur fundi/maja
ishte para orarit të tregtimit (si 10 dhe 11 qershor).

**Ditët me trend** (vetëm SELL ose vetëm BUY, si 1 dhe 2 shtator): pasi çmimi ka rënë ≥ 0.45 × ADR
nga maja dhe s'bën kthim të madh, boti **shet rikthimin e vogël** (pullback 10–35% e ADR) kur ai
refuzohet, me SL mbi rikthimin. Në ditët me trend lart, blen rënien e vogël. Kështu tregton edhe
me trendin, jo vetëm kundër tij.

- **SL**: pak mbi majë / nën fund (+0.3 × ATR). Min 3$, max 25$ (nëse del më i madh, trade-i anulohet).
- **Dalja si snajper (trailing stop)**: pa TP fiks. Kur fitimi arrin 1 × SL, SL-ja shkon në hyrje
  (break-even). Pastaj SL-ja ndjek çmimin më të mirë me distancë **0.4 × ADR (~40$)**, pra trade-i
  mbyllet vetëm kur lëkundja e ditës kthehet vërtet. Kështu boti e kalëron lëvizjen e plotë,
  si 19 gushti (+203$) ose 2 shtatori.
- Vetëm 1 pozicion njëherësh, max 4 trade në ditë, stop nëse humbja ditore arrin 3%.
- Tregton 01:00–20:00 UTC (= 04:00–23:00 në orën e grafikut IC Markets).

### Rezultati në 120 ditët e fundit (të dhëna reale M15 nga llogaria jote)

| | **Sniper (fillestar)**: tipi i ditës + trailing | Vetëm trailing | TP fiks 1:3 (`TRAIL_ADR=0`) |
|---|---|---|---|
| Trade në ditë (mesatarisht) | 2.8 | 2.6 | 3.4 |
| Ditë me ≥ 2 trade | 82% | 75% | 91% |
| Totali | **+78.7R** | +61.2R | +52.9R |
| 60 ditët e para / 60 të fundit | **+46.4R / +20.1R** | +38.6R / +12.9R | +24.8R / +34.1R |
| Drawdown max | **13.9R** | 14.8R | 17.8R |
| Trade-i më i mirë | **+18.6R** | +18.6R | +3R |

Në ditët nga screenshot-et (10, 11, 12, 15 qershor; 17, 18 gusht; 1, 2, 25 shtator): **+34.1R**
(10 qershor +13.3R, 2 shtator +16.5R, 18 gusht +7.3R).

Me 0.5% rrezik për trade, fillestari del rreth +39% në 120 ditë, me drawdown max rreth 7%.
Rezultati ndryshon ±10R sipas dritares së saktë të 120 ditëve. Rezultatet e kaluara nuk garantojnë të ardhmen.

Me trailing boti bën më pak trade, sepse mban një pozicion gjatë një lëvizjeje të madhe.
Provova të lejoj një pozicion të dytë kur i pari është pa rrezik (`MAX_POSITIONS=2`):
3.6 trade/ditë, por vetëm +43R dhe drawdown 25R. Prandaj fillestari mbetet 1 pozicion.
Provova edhe mbylljen dhe kthimin e pozicionit kur vjen sinjal i kundërt: e ul fitimin (+19R deri +63R).

Nga 27 majat/fundet që shënove, **19 janë saktësisht majat/fundet që gjen boti** në lëkundjet e ditës,
dhe në 14 prej tyre boti hyn direkt në trade. Të tjerat i humb kur lëvizja para tyre ishte pak nën 0.45 × ADR
ose kur kthimi s'ka bisht dhe konfirmohet më vonë se 2 qirinj. Uljet e këtyre pragjeve
në backtest i shtojnë humbjet më shumë se fitimet.
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
| `MODE` | `sniper` | `klasik` = modeli i vjetër (32 qirinj + RSI 65/35) |
| `SWING_REV` | `0.4` | sa × ADR duhet të kthehet çmimi që të konfirmohet një majë/fund |
| `LEG_MIN_ADR` | `0.45` | lëvizja minimale para majës/fundit (× ADR) |
| `CONFIRM_BARS` | `2` | sa qirinj pas majës/fundit pritet konfirmimi |
| `TREND_ENTRIES` | `true` | tregto edhe me trendin në ditët me një drejtim (`false` = vetëm maja/funde) |
| `PULL_MIN_ADR` / `PULL_MAX_ADR` | `0.10` / `0.35` | madhësia e pullback-ut në ditët me trend (× ADR) |
| `ADR_DAYS` | `10` | sa ditë për mesataren e lëvizjes ditore |
| `DRY_RUN` | `false` | `true` = vetëm sinjale në log, pa trade |
| `RISK_PERCENT` | `0.5` | % e balancës që rrezikohet për trade |
| `FIXED_LOTS` | `0` | nëse > 0, përdor gjithmonë këtë lot (p.sh. `0.05`) |
| `MAX_LOTS` | `1.0` | loti maksimal për trade (mbrojtje) |
| `EARLY_TREND_ADR` | `0.4` | 8 orët e para ≥ kaq × ADR → ditë trendi (`0` = joaktiv) |
| `TREND_DAY_ADR` | `0.5` | çmimi ≥ kaq × ADR larg hapjes së ditës → ditë trendi në atë moment (`0` = joaktiv) |
| `ROT_DAY_ADR` | `0.2` | 8 orët e para < kaq × ADR → ditë rotacioni (`0` = joaktiv) |
| `ROT_TP_ADR` | `0.3` | TP në ditët e rotacionit (× ADR) |
| `TRAIL_ADR` | `0.4` | distanca e trailing stop (× ADR); `0` = TP fiks me `RR` |
| `TRAIL_START_R` | `1.0` | trailing fillon pasi fitimi arrin kaq R |
| `MAX_POSITIONS` | `1` | `2` = pozicion i dytë kur i pari është pa rrezik (në backtest ul fitimin) |
| `RR` | `3.0` | TP = SL × RR (vetëm kur `TRAIL_ADR=0`) |
| `BREAK_EVEN_R` | `1.0` | SL në hyrje pas kaq R fitim (`0` = joaktiv) |
| `MAX_DAILY_LOSS_PCT` | `3.0` | stop për sot pas kaq % humbje |
| `MAX_TRADES_PER_DAY` | `4` | trade maksimale në ditë |
| `MIN_SL` / `MAX_SL` | `3` / `25` | kufijtë e SL në $ |
| `START_HOUR_UTC` / `END_HOUR_UTC` | `1` / `20` | orari i tregtimit (UTC) |
| `MAX_SPREAD` | `0.5` | spread maksimal në $ |
| `LOOKBACK` | `32` | vetëm `klasik`: sa qirinj për majë/fund |
| `MIN_LEG_ATR` | `3.0` | vetëm `klasik`: lëvizja minimale (× ATR) |
| `MIN_WICK_PCT` | `40` | bishti minimal i qirit të refuzimit (%) |
| `RSI_OVERBOUGHT` / `RSI_OVERSOLD` | `65` / `35` | vetëm `klasik`: filtri RSI |
| `USE_RSI` | `true` | vetëm `klasik`: çaktivizo RSI me `false` |
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
cbot/GoldSniper.cs modeli klasik si cBot për cTrader Desktop (opsionale, nëse ke kompjuter)
```
