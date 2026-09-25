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
gjatë ditës:

| Kushti | Tipi | Çfarë bën boti |
|---|---|---|
| Në çdo moment çmimi është ≥ 0.7 × ADR (~70$) larg hapjes së ditës | **DITË TRENDI** | vetëm trade në drejtimin e ditës, dalje me trailing |
| 8 orët e para (00:00–08:00 ora e grafikut) lëvizin < 0.2 × ADR, dhe dita s'është bërë trend | **DITË ROTACIONI** (81% nuk bëjnë trend) | BUY dhe SELL, TP i vogël 0.3 × ADR (~30$) |
| asnjëra | e paqartë | të dyja drejtimet, dalje me trailing |

Rregulli "në çdo moment" e kap ditën e trendit edhe kur ai fillon vonë ose kur fundi/maja
ishte para orarit të tregtimit (si 10 dhe 11 qershor). Një rregull që e caktonte trendin nga
8 orët e para dukej mirë në qershor–shtator, por humbi para në shkurt–maj, prandaj u hoq.

**Ditët me trend** (vetëm SELL ose vetëm BUY, si 1 dhe 2 shtator): pasi çmimi ka rënë ≥ 0.45 × ADR
nga maja dhe s'bën kthim të madh, boti **shet rikthimin e vogël** (pullback 10–35% e ADR) kur ai
refuzohet, me SL mbi rikthimin. Në ditët me trend lart, blen rënien e vogël. Kështu tregton edhe
me trendin, jo vetëm kundër tij.

- **SL**: pak mbi majë / nën fund (+0.3 × ATR). Min 3$, max 25$ (nëse del më i madh, trade-i anulohet).
- **Dalja si snajper (trailing stop)**: pa TP fiks. Kur fitimi arrin 1 × SL, SL-ja shkon në hyrje
  (break-even). Pastaj SL-ja ndjek çmimin më të mirë me distancë **0.4 × ADR (~40$)**, pra trade-i
  mbyllet vetëm kur lëkundja e ditës kthehet vërtet. Kështu boti e kalëron lëvizjen e plotë,
  si 19 gushti (+203$) ose 2 shtatori. **Në ditët e trendit** (në drejtimin e trade-it) distanca
  bëhet **0.8 × ADR**, që trade-i të mos dalë nga një rikthim i zakonshëm i trendit.
- Vetëm 1 pozicion njëherësh, max 4 trade në ditë, stop nëse humbja ditore arrin 3%.
- Tregton 01:00–20:00 UTC (= 04:00–23:00 në orën e grafikut IC Markets).

### Rezultati në 8 muaj (28 janar – 25 shtator, të dhëna reale M15 nga llogaria jote)

Rregullat u ndërtuan me të dhënat e qershorit–shtatorit. Shkurti–maji nuk u përdorën fare për
t'i zgjedhur, prandaj ai është testi i ndershëm ("jashtë mostrës"): si do dilte boti në muaj
që s'i ka parë kurrë.

| | **Sniper (fillestar)** | Gjuetar trendi (`TRAIL_ADR=0.6`) | TP fiks 1:3 (`TRAIL_ADR=0`) | `MODE=klasik` |
|---|---|---|---|---|
| **Shkurt–maj (jashtë mostrës)** | **+36.1R** (DD 20.9R) | +140.6R (DD 15.3R) | −6.6R | −10.3R |
| Qershor–shtator (ku u ndërtua) | **+84.7R** (DD 14.8R) | +32.1R (DD 14.9R) | +49.9R | +28.4R |
| **8 muaj gjithsej** | +104.6R (DD 20.9R) | **+152.8R** (DD 23.4R) | +35.4R | +17.1R |
| Trade në ditë | 2.8 | 2.4 | 3.3 | 2.0 |
| Ditë me ≥ 2 trade | 79% | 69% | 89% | 58% |

**Sniper (fillestar)** del mirë në të dy periudhat. **Gjuetari i trendit** mban trailing të gjerë
(0.6 × ADR) në çdo trade: në muajt me trende të mëdha (shkurt–maj) fiton shumë më tepër, p.sh. 20 marsi
+18.5R (gjithë rënia 240$) në vend të +1.9R, por në muajt më të qetë (qershor–shtator) fiton shumë më pak.
Zgjidhe sipas tregut: vendos `TRAIL_ADR=0.6` në Railway kur ari bën trende të mëdha.

8 muaj, sniper: 488 trade, 87 fitime, 160 break-even, 241 humbje; trade-i më i mirë +25.2R.

Çfarë tregon kjo:
- Boti mbetet fitimprurës në muajt që s'i ka parë, por **më pak** se në muajt ku u ndërtua.
  Prit rezultate më afër shkurt–majit sesa qershor–shtatorit.
- **Trailing stop-i është pjesa që funksionon vërtet**: pa të, çdo version humbet jashtë mostrës.
- Drawdown-i max në 8 muaj ishte **20.9R**. Me 0.5% rrezik kjo është rreth −10% nga maja e llogarisë.
  Shumica e trade-ve humbin ose dalin në break-even; fitimi vjen nga pak trade të mëdha.
- Rezultatet e kaluara nuk garantojnë të ardhmen.

Me 0.5% rrezik për trade, 8 muajt dalin rreth +52% (gjuetari i trendit rreth +76%).

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
| `TREND_DAY_ADR` | `0.7` | çmimi ≥ kaq × ADR larg hapjes së ditës → ditë trendi në atë moment (`0` = joaktiv) |
| `EARLY_TREND_ADR` | `0` | 8 orët e para ≥ kaq × ADR → ditë trendi (joaktiv; humbi jashtë mostrës) |
| `ROT_DAY_ADR` | `0.2` | 8 orët e para < kaq × ADR → ditë rotacioni (`0` = joaktiv) |
| `ROT_TP_ADR` | `0.3` | TP në ditët e rotacionit (× ADR) |
| `TREND_TRAIL_ADR` | `0.8` | trailing në ditët e trendit, në drejtimin e trade-it (× ADR; `0` = si `TRAIL_ADR`) |
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
