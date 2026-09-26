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
SELL), ose rotacion (BUY-SELL-BUY-SELL). Boti e dallon vetë, pa ndihmën tënde, me aritmetikën e ditës:

**Eficienca e ditës** = |çmimi − hapja| / rruga e përshkuar (shuma e lëvizjeve të çdo qiriri).
Trendi lëviz drejt (eficiencë e lartë), rotacioni shkon lart-poshtë (eficiencë e ulët).
U mat në 164 ditë (8 muaj), 6 orë pas hapjes së ditës:

| Eficienca pas 6 orëve | Sa mbarojnë trend (shkurt–maj / qershor–shtator) |
|---|---|
| < 0.15 | **4% / 18%** → pothuajse gjithmonë rotacion |
| 0.15 – 0.30 | 31% / 19% |
| ≥ 0.30 | 38% / 62% |

Rregullat e botit:

| Kushti | Tipi | Çfarë bën boti |
|---|---|---|
| Çmimi është ≥ 0.7 × ADR (~70$) larg hapjes së ditës | **DITË TRENDI** | vetëm trade në drejtimin e ditës; trailing i gjerë 0.8 × ADR |
| Pas 6 orëve eficienca < 0.15, ose pas 8 orëve lëvizja < 0.2 × ADR | **DITË ROTACIONI** | BUY dhe SELL, TP 0.3 × ADR (~30–50$ në çdo leg) |
| asnjëra | e paqartë | të dyja drejtimet, trailing 0.4 × ADR |

**Trade trendi mbetet trade trendi.** Kur një trade njihet si trend (dita tregon trend në drejtimin
e tij), ai mban trailing-un e gjerë deri në mbyllje. Pa këtë, sa herë vinte një rikthim, çmimi afrohej
te hapja, sinjali i trendit fikej dhe trailing-u ngushtohej pikërisht kur trade-i kishte nevojë për
hapësirë.

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
- Vetëm 1 pozicion sniper njëherësh (konfluenca dhe hierarkia kanë pozicionin e tyre), max 4 trade sniper në ditë,
  stop për të dy modulet nëse humbja ditore arrin 3%.
- **E premte 19:00 UTC (22:00 ora e grafikut):** mbyll gjithçka dhe s'hap trade të reja deri të hënën.
  Pa këtë, një trade i së premtes mbahej gjithë fundjavën dhe e hënën (rrezik gap-i të hënën në mëngjes).
- Tregton 01:00–20:00 UTC (= 04:00–23:00 në orën e grafikut IC Markets).

### Rezultati në 8 muaj (28 janar – 25 shtator, të dhëna reale M15 nga llogaria jote)

Rregullat u ndërtuan me të dhënat e qershorit–shtatorit. Shkurti–maji nuk u përdorën fare për
t'i zgjedhur, prandaj ai është testi i ndershëm ("jashtë mostrës"): si do dilte boti në muaj
që s'i ka parë kurrë.

| | **Sniper (fillestar)** | Sniper pa eficiencë dhe pa "trade trendi" | TP fiks 1:3 (`TRAIL_ADR=0`) | `MODE=klasik` |
|---|---|---|---|---|
| **Shkurt–maj (jashtë mostrës)** | **+97.9R** | +36.1R | −6.6R | −10.3R |
| Qershor–shtator (ku u ndërtua) | +74.1R | **+84.7R** | +49.9R | +28.4R |
| **8 muaj gjithsej** | **+150.3R** (DD 21.4R) | +104.6R (DD 20.9R) | +35.4R | +17.1R |
| Trade në ditë | 2.7 | 2.8 | 3.3 | 2.0 |

Sipas muajve (fillestari): shkurt +15.5R, mars +26.8R, prill +30.9R, maj +20.7R, qershor +11.2R,
korrik +4.0R, gusht +26.8R, shtator +14.5R. **Të 8 muajt fitimprurës.**

8 muaj, sniper: 471 trade, 89 fitime, 149 break-even, 233 humbje; trade-i më i mirë +27.5R.

Çfarë tregon kjo:
- Boti mbetet fitimprurës në muajt që s'i ka parë, por **më pak** se në muajt ku u ndërtua.
  Prit rezultate më afër shkurt–majit sesa qershor–shtatorit.
- **Trailing stop-i është pjesa që funksionon vërtet**: pa të, çdo version humbet jashtë mostrës.
- Drawdown-i max në 8 muaj ishte **21.4R**. Me 0.5% rrezik kjo është rreth −11% nga maja e llogarisë.
  Shumica e trade-ve humbin ose dalin në break-even; fitimi vjen nga pak trade të mëdha.
- Rezultatet e kaluara nuk garantojnë të ardhmen.

Me 0.5% rrezik për trade, 8 muajt dalin rreth +75%.

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

### Moduli i dytë: KONFLUENCA (analiza jote me shumë kohë)

Kjo është metoda jote e kthyer në rregull: një nivel **H1/H4** + zona **fresh** (të paprekura)
të kohëve të ulëta në të njëjtin vend + trendline M30 + **rejection në M5**.

- Çdo 5 minuta boti lexon qirinjtë M5 dhe prej tyre ndërton M15, M30, H1 dhe H4.
- Në çdo kohë gjen zonat supply/demand (qiri bazë para një lëvizjeje ≥ 1.5 × ATR), edhe zonat
  e thyera që kthehen në anën tjetër (demand i thyer → supply), dhe trendline-t M30 nga mbylljet.
- Një zonë vlen vetëm deri në prekjen e parë (**fresh / unmitigated**) dhe jo më e vjetër se 10 ditë.
- **Hyrja:** një qiri M5 me wick ≥ 50% prek njëkohësisht **≥ 4 nivele** (kohë të ndryshme + trendline),
  të paktën njëri H1 ose H4, dhe mbyllet në gjysmën tjetër të qirit → hyrje në mbylljen e qirit.
- **SL:** 0.5$ pas wick-ut të rejection-it (max 20$). **TP:** niveli fresh më i afërt përballë
  (zonë M15/M30/H1/H4 ose trendline), vetëm nëse është të paktën **3R** larg; përndryshe s'ka trade.
- Ka pozicionin e vet (label `GoldSniper-C`), të pavarur nga moduli sniper. SL dhe TP janë fikse:
  pa break-even dhe pa trailing. Respekton orarin, spread-in, limitin ditor dhe mbylljen e së premtes.
- Në Telegram mesazhi tregon nivelet, p.sh. `KONFLUENCE: H1+M15+M30+TL + rejection M5`.

| 8 muaj (M5 nga llogaria) | Trade | Rezultati | Shk–maj | Qer–sht |
|---|---|---|---|---|
| Konfluencë ≥ 2 nivele | 319 | −9.6R | | |
| Konfluencë ≥ 3 nivele | 161 | +19.8R | | |
| **Konfluencë ≥ 4 nivele** (fillestari) | **64** | **+23.3R** (DD 11.0R) | +13.7R | +9.6R |
| Sniper vetëm | 471 | +150.3R (DD 21.4R) | +97.9R | +52.4R |
| **Sniper + konfluencë bashkë** | **535** | **+173.7R (DD 20.0R)** | +111.6R | +62.0R |

Sa më shumë nivele bashkohen, aq më mirë del — pikërisht si në analizën tënde.
Bashkë me sniper-in fitimi rritet, drawdown-i ulet dhe muaji më i keq bëhet +11.4R (në vend të +4.0R);
të 8 muajt fitimprurës. Por vetë moduli ka muaj me humbje (mars −5.0R, prill −4.0R, shtator −1.8R)
dhe vetëm ~2 trade në javë, prandaj 64 trade janë ende pak për një gjykim të sigurt.
Nuk i kap të gjitha shembujt e tu: kur një setup ka më pak se 4 nivele ose TP-ja është nën 3R, e lë.
Për ta fikur: `CONFLUENCE=false`.

### Moduli i tretë: HIERARKIA (muri H1 → konfirmimet → hyrja)

Logjika jote hap pas hapi. Tregu lëviz nga blerësit dhe shitësit: nëse çmimi prek një zonë
**H1** supply/demand dhe **s'e thyen dot**, ai s'ka forcë në atë drejtim. Pastaj vijnë konfirmimet:

1. **Muri H1**: prekja e parë e një zone H1 (fresh), pa asnjë mbyllje përtej saj.
2. Brenda 8 orëve pas prekjes: **thyerje strukture M5** (mbyllje nën swing low-in e fundit para majës,
   pra demand-i M5 i thyer) **dhe divergjencë AO në M5** (maja më e lartë, AO më i ulët).
3. **Rejection M5** → hyrje në mbylljen e qirit. SL pas wick-ut (minimumi 3$), TP te niveli
   fresh përballë (zonë M15/M30/H1/H4 ose trendline), të paktën **2R** larg.
4. Pozicion i vetin (label `GoldSniper-H`), SL/TP fikse, pa trailing.
5. Në Telegram shfaqen konfirmimet: `HIERARKIA: muri H1 s'u thye + thyerje strukture M5 + divergjence AO + … + rejection M5`.

| 8 muaj (M5 nga llogaria) | Trade | Rezultati | Drawdown | Shk–maj | Qer–sht |
|---|---|---|---|---|---|
| **Hierarkia** (H1 + thyerje + AO) | 233 | **+95.6R** | 14.8R | +37.0R | +58.6R |
| Hierarkia me slippage 0.3$ | 233 | +80.5R | 15.2R | +31.4R | +49.1R |
| Muri H4 në vend të H1 | 87 | −9.5R | | | |
| **Sniper + konfluencë + hierarki** | **768** | **+269.2R** | **18.8R** | +148.7R | +120.6R |

Të tre modulet bashkë: të 8 muajt fitimprurës (më i keqi +14.3R), drawdown më i vogël se sniper-i vetëm (18.8R, trade-t e renditura sipas daljes).

Nga konfirmimet që provova veç e veç, **divergjenca AO** dhe **zona M5 e thyer** kanë avantazh.
QM dhe trendline-i si konfirmim i vetëm dolën negativë në këtë kod. Edhe kjo metodë fiton nga pak
trade të mëdha: SL i vogël dhe TP larg. Pa 10 trade-t më të mira rezultati është afër zeros,
prandaj duhen javë të tëra për ta gjykuar. Për ta fikur: `HIERARCHY=false`.

Kodet e kërkimit për setup-et e tua janë në `research/` (Quasimodo H1+M5, trendline 3rd touch, konfluenca, hierarkia).

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

### Fundjava: BTCUSD (e shtunë dhe e diel)

Ari është i mbyllur në fundjavë, prandaj boti kalon vetë te **BTCUSD**:

- **E shtunë 00:00 UTC → e diel 21:00 UTC** tregton BTCUSD me të njëjtat tre module.
- **E diel 21:00 UTC** mbyll pozicionet BTC; **të hënën** kthehet te XAUUSD si gjithmonë.
- Loti i kriptos është ndryshe: 1 lot = 1 BTC (`volume 100`), ndërsa 1 lot ari = 100 oz (`volume 10000`).
  Boti e llogarit vetë sipas simbolit.
- BTC lëviz ~20 herë më shumë se ari në ditë, prandaj të gjitha vlerat në $ shumëzohen me 20
  (SL min 60$, max 500$, spread max 10$). Strategjitë bazohen në ADR, kështu që përshtaten vetë.
- Në Telegram vjen 🔄 kur ndërron tregu, dhe mesazhet e trade-ve tregojnë BTCUSD.

**Kujdes:** në backtest (8 muaj, vetëm të shtunat dhe të dielat) BTC s'ka avantazh të qartë:

| Moduli | 8 muaj | Shk–maj | Qer–sht |
|---|---|---|---|
| Sniper | 169 trade, +17.1R | +21.0R | −3.8R |
| Hierarkia | 49 trade, +6.5R | +10.5R | −4.0R |
| Konfluenca | 37 trade, +3.6R | +10.8R | −7.2R |

Katër muajt e fundit dolën negativë për të tre modulet, dhe vetëm rreth 1 në 3 fundjava fitoi.
Prandaj rreziku për BTC fillon te **0.25%** (gjysma e arit). Për ta fikur: `BTC_WEEKEND=false`.

### Njoftimet në Telegram

Boti të shkruan në Telegram, që s'ke nevojë të hapësh Railway:

| Mesazhi | Kur |
|---|---|
| 🟢 Gold Sniper u nis | pas çdo nisjeje/rinisjeje në Railway |
| 🎯 BUY / SELL | hapet një trade (çmimi, SL, TP ose trailing, tipi i ditës ose nivelet e konfluencës) |
| 🔒 SL në hyrje | trade-i s'mund të humbasë më |
| 📈 Fitim i siguruar +XR | SL-ja ngjitet çdo +2R |
| ✅ / ❌ U mbyll | rezultati në R dhe në EUR, balanca e re |
| 📊 Përmbledhja e ditës | në fund të çdo dite me trade |
| ⚠️ / 🛑 | cTrader s'përgjigjet > 5 min, SL s'u vendos, u arrit humbja max ditore |

Shkruaji botit **/status** në Telegram: të tregon balancën, pozicionin e hapur dhe tipin e ditës.
Komandat vetëm lexojnë; nga Telegram-i nuk mund të hapet ose mbyllet asnjë trade,
dhe boti u përgjigjet vetëm mesazheve nga chat-i yt.

Nëse në log shfaqet `Telegram 409 Conflict`: një program tjetër po lexon mesazhet e të njëjtit bot
(p.sh. një deployment i dytë në Railway, ose një aplikacion tjetër me të njëjtin token). Njoftimet vijnë
gjithsesi; vetëm `/status` mund të mos përgjigjet. Zgjidhja: një token vetëm për këtë bot (krijo një bot
të ri te @BotFather) dhe një service i vetëm në Railway.

Vendosja:
1. Në Telegram hap botin tënd dhe shtyp **Start** (një bot s'mund të të shkruajë para kësaj).
2. Railway → **Variables** → shto `TELEGRAM_TOKEN` (tokeni nga @BotFather) dhe `TELEGRAM_CHAT_ID`.
3. Railway e rinis botin; brenda pak sekondash duhet të vijë mesazhi 🟢 Gold Sniper u nis.

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
| `TELEGRAM_TOKEN` | – | tokeni i botit tënd të Telegram-it (nga @BotFather) |
| `TELEGRAM_CHAT_ID` | – | ID e chat-it ku vijnë njoftimet |
| `DRY_RUN` | `false` | `true` = vetëm sinjale në log, pa trade |
| `RISK_PERCENT` | `0.5` | % e balancës që rrezikohet për trade |
| `FIXED_LOTS` | `0` | nëse > 0, përdor gjithmonë këtë lot (p.sh. `0.05`) |
| `MAX_LOTS` | `1.0` | loti maksimal për trade (mbrojtje) |
| `TREND_DAY_ADR` | `0.7` | çmimi ≥ kaq × ADR larg hapjes së ditës → ditë trendi në atë moment (`0` = joaktiv) |
| `EARLY_TREND_ADR` | `0` | 8 orët e para ≥ kaq × ADR → ditë trendi (joaktiv; humbi jashtë mostrës) |
| `EFF_ROT` | `0.15` | eficienca e ditës pas 6 orëve < kaq → ditë rotacioni (`0` = joaktiv) |
| `CLOSE_FRIDAY_UTC` | `19` | të premten në këtë orë UTC mbyll gjithçka, pa trade deri të hënën (`-1` = joaktiv) |
| `STICKY_TREND` | `true` | trade-i që njihet si trend mban trailing-un e gjerë deri në mbyllje |
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
| `CONFLUENCE` | `true` | moduli i dytë i konfluencës (`false` = vetëm sniper) |
| `CONF_MIN_LEVELS` | `4` | sa nivele fresh duhet të bashkohen (3 = më shumë trade, më pak fitim për trade) |
| `CONF_RR` | `3.0` | TP i konfluencës duhet të jetë të paktën kaq R larg |
| `HIERARCHY` | `true` | moduli i tretë i hierarkisë (`false` = joaktiv) |
| `HIER_RR` | `2.0` | TP i hierarkisë duhet të jetë të paktën kaq R larg |
| `HIER_MIN_SL` | `3.0` | SL minimal i hierarkisë në $ |
| `BTC_WEEKEND` | `true` | BTCUSD të shtunën dhe të dielën (`false` = fundjava pa tregtim) |
| `BTC_RISK_PERCENT` | `0.25` | rreziku për trade në BTC (%) |
| `BTC_MAX_LOTS` | si `MAX_LOTS` | loti maksimal për BTC (1 lot = 1 BTC) |
| `BTC_SCALE` | `20` | vlerat në $ të arit × kaq për BTC |
| `BTC_CLOSE_SUNDAY_UTC` | `21` | ora e së dielës (UTC) kur mbyllen pozicionet BTC |

Llogaria jote demo ka balancë shumë të madhe, prandaj me 0.5% rrezik loti del gjithmonë
te kufiri `MAX_LOTS`. Rregulloje `MAX_LOTS` ose përdor `FIXED_LOTS` sipas dëshirës.

## Struktura

```
bot/main.py        boti live (cikli, urdhrat, break-even, limiti ditor, faqja e statusit)
bot/strategy.py    zbulimi i majave/fundeve
bot/mcp_client.py  lidhja me cTrader Trading MCP
bot/data.py        marrja e qirinjve (M15, M5)
bot/zones.py       zonat supply/demand fresh, zonat e thyera (flip), swing-et
bot/confluence.py  moduli i konfluences (H1/H4 + zona fresh + trendline + rejection M5)
bot/hierarchy.py   moduli i hierarkise (muri H1 + thyerje strukture M5 + divergjence AO + rejection M5)
bot/markets.py     tregjet: XAUUSD e hene-e premte, BTCUSD te shtunen dhe te dielen
bot/telegram.py    njoftimet dhe komanda /status
bot/config.py      parametrat nga variablat e mjedisit
backtest.py        backtest me të dhënat reale
research/          prototipet e setup-eve (Quasimodo, trendline 3rd touch, konfluenca)
cbot/GoldSniper.cs modeli klasik si cBot për cTrader Desktop (opsionale, nëse ke kompjuter)
```
