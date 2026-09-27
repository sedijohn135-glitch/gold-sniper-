# Plani i testit live në demo (28 shtator – 23 tetor 2026)

Qëllimi: të shohim nëse secili modul sillet live si në backtest. Ky dokument
mjafton që çdokush (edhe një bisedë e re me Claude) ta vazhdojë analizën.

## Si mblidhen të dhënat

- Boti dërgon në Telegram **📒 raportin javor**: e premte 22:50 (XAUUSD) dhe e diel 22:50 (BTCUSD),
  ora e Kosovës/Shqipërisë. Pronari i kopjon në Notes dhe i ngjit në fund të testit.
- Çdo raport ka trade-t, rezultatin në R dhe EUR, dhe **ndarjen sipas modulit**. Fitimi në EUR vjen nga
  deal-et e cTrader-it, pra është i saktë edhe pas rinisjeve. Moduli dhe R-ja ruhen te `/data/state.json`
  (volume në Railway); pa volume, pas një deploy-i gjatë javës moduli i trade-ve të mëparshme del "i panjohur".
- Burimi zyrtar për çdo mosmarrëveshje: cTrader → History / Statement.
- Railway: trial deri më 22 tetor ose deri sa mbarojnë kreditet ($4.77 më 27 shtator). Për javën e 4-t
  duhet plani Hobby, përndryshe testi ka ~3.5 javë.

## Çfarë pritet nga backtest-i (8 muaj ari, 26 jan – 25 sht 2026)

| Moduli | Trade/javë | R/javë | Fitime | 4 javë: mesatarja | 4 javë: më e keqja | 4-javshe negative |
|---|---|---|---|---|---|---|
| Sniper (trend/rotacion, ADR) | 13.5 | +4.3R | 19% | +18.8R | −9.2R | 3 nga 30 |
| Hierarkia (H1 + thyerje + AO/SBR) | 9.6 | +3.5R | 26% | +15.5R | −11.2R | 7 nga 30 |
| Konfluenca (≥4 zona + rejection) | 1.8 | +0.7R | 20% | +3.2R | −9.0R | 11 nga 30 |
| Lajmi (CPI/NFP/FOMC) | 0.7 | +0.7R | 32% | +3.2R | −3.0R | 7 nga 30 |
| **Të gjitha bashkë** | ~25 | ~+9R | | **+39.5R** | **+6.0R** | **0 nga 32** |

BTC në fundjavë (0.25% rrezik): pa avantazh të qartë në backtest (sniper +17R, hierarkia +6.5R,
konfluenca +3.6R në 8 muaj, të gjitha negative qershor–shtator). Vlerësohet veç, jo bashkë me arin.

Fitimi vjen nga pak trade të mëdha: 1 në 4–5 trade fiton, shumica dalin −1R ose në break-even.
Një javë e keqe (deri −13R te sniper-i) është normale edhe në backtest.

## Si gjykohet pas 4 javësh (vetëm ari)

1. **Të gjitha bashkë:** në backtest asnjë periudhë 4-javore s'ishte negative (më e keqja +6R).
   Nëse live del negative, diçka nuk po punon si në backtest: kontrollo slippage-in, spread-in dhe
   trade-t që s'kanë ndodhur si duhej, para se të ndryshohet strategjia.
2. **Secili modul:** krahaso R-në e 4 javëve me kolonat më sipër.
   - Mbi mesataren ose afër saj → mbetet.
   - Mes mesatares dhe "më e keqja" → normale, vazhdo testin.
   - Nën "më e keqja" e backtest-it → shenjë e keqe: fike modulin (`CONFLUENCE=false`,
     `HIERARCHY=false`, `NEWS=false`) dhe shqyrto trade-t e tij një nga një.
3. **Mos gjyko nga një trade ose një ditë.** Me 19–26% fitime, 4 javë janë ende pak për modulet e rralla
   (konfluenca ~7 trade, lajmi ~3 trade në 4 javë): për to duhen 2–3 muaj.
4. **Dallimet live vs backtest që duhen shënuar:** slippage në SL (te BTC u pa 18–55$), trade të dyfishta,
   pozicione pa SL, mesazhe që mungojnë në Telegram.

## Gjendja e botit në fillim të testit (commit c5f7030)

- XAUUSD e hënë–e premte: Sniper + Konfluenca + Hierarkia + Lajmi, rrezik 0.5% për trade, max 1 lot.
- BTCUSD e shtunë 00:00 – e diel 21:00 UTC: të njëjtat module me vlerat $ × 20, rrezik 0.25%.
- Setup-et e pronarit dhe çfarë u testua: `research/SETUPS.md`. Si funksionon boti: `README.md`.
