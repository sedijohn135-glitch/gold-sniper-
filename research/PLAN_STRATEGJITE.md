# Plani: 20 PDF-të e strategjive → kod (1 tetor 2026)

## Çfarë ka në 20 PDF-të (17 të ndryshme, 3 dublikata)

| Familja | PDF-të | Çfarë thonë (shkurt) |
|---|---|---|
| **A. SNR Malajzian** | SNR Malaysia, My Rare SnR Course 2, MSNR, MSNR SL 10 pips, MSNR x Alchemist, Alchemist, Secret of 411 (trendline) | Nivele nga TRUPI i qirinjve, jo nga bishti: A = mbyllja bullish → hapja bearish (rezistencë), V = mbyllja bearish → hapja bullish (support), GAP SNR (2 qirinj momentumi të kundërt), Doji SNR. **Fresh** = asnjë bisht s'e ka prekur; prekja e parë duhet të jetë BISHT (trupi = e pavlefshme); **MISS** = qirinjtë pas nivelit s'e prekin (e forcon). Thyerje me trup → flip (RBS/SBR). Trendline mbi pikat A/V, hyrje vetëm në **pikën 3**; **"X factor"** = ku trendline pret SNR-në horizontale. QML/QMX, engulfing te maja, OCL. MTF: setup H4/D1 → rejection → thyerje 2 TF më poshtë → hyrje në retest; SL pas bishtit; TP te SNR-ja fresh e radhës. Seancat London/NY. |
| **B. Trendline Breakout** | Trendline Breakout (forextrendlinetrading) | H1: qiri mbyllet përtej trendline-s → stop order pak përtej qirit; ose pullback te vija + qiri kthimi. SL pas qirit, TP te maja/fundi i mëparshëm, BE në 1R, trailing pas çdo maje/fundi. |
| **C. ICT / Quarterly Theory** | Quarterly Theory (×2), Free QT Sinzo, QT Continuation, QT model 1 (×2), OSOK, PSP (×2), ERL-IRL, MMXM | Koha ndahet në çerekë (vit/muaj/javë/ditë/90 min); "true open" = hapja e Q2 (dita 00:00 NY). **PSP/SSMT** = divergjencë mes aseteve të lidhura (ari–argjendi–DXY) te maja/fundi. ERL→IRL: pas marrjes së likuiditetit (maja/fundi) synohet FVG, e anasjellta. MMXM: konsolidim → manipulim → shpërndarje, me Fibonacci. |
| **D. Time & Price** | Time and Price | Kill zones (London 2–5, NY 7–10 ora NY), shmang lajmet CPI/FOMC/NFP/PPI, shit mbi true day open, bli nën të; RR 1:2. |
| **E. Psikologjia** | pjesë në 411, Trendline, Rare SnR | Rregulla disipline, RR 1:2–1:5. S'kodohet. |

## Çfarë është testuar tashmë (që mos e përsërisim)
SNR breakout+retest nga swing H1, flip levels, RBR/DBD, S/D bazë, 4,096 kombinime konfluencash, QM (M5/M15/H1/H4),
trendline prekja e 3-të (M15–H4), engulfing H4/H1/M30 me zona (ZONA SNIPER), lajmet, ORB 9:27, overnight range.
Asnjë s'doli i qëndrueshëm në 10 vjet. **E patestuar**: nivelet nga TRUPI (A/V/GAP) me rregullat fresh / prekje me bisht / MISS,
"X factor" (trendline × SNR) në pikën 3, divergjenca ari–argjend (SMT), çerekët e kohës dhe true open.

## Fazat

**Faza 0 — filtra të shpejtë mbi sniper-in (1 seancë)**
1. True day open: SELL vetëm mbi hapjen 00:00 NY, BUY vetëm nën të.
2. Kill zones: hyrje vetëm London (08:00–11:00) dhe NY (13:00–17:00) ora e Shqipërisë.
3. Pa hyrje 30 min para/pas lajmeve të mëdha (orët fikse 8:30/10:00/14:00 NY, si në `research/news.py`).

**Faza 1 — motori SNR Malajzian (2–3 seanca)**: `bot/msnr.py`
1. Nivelet A/V/GAP/Doji nga trupat në D1/H4/H1/M15, me gjendjen fresh/unfresh, numrin e prekjeve dhe MISS.
2. Trendline mbi pikat A/V (≥2 pika, pa mbyllje përtej), pika 3 dhe kryqëzimi me SNR ("X factor").
3. Setup: prekja e parë me bisht e një niveli fresh HTF (+ X factor si pikë shtesë) → thyerje në TF 2 shkallë më poshtë → hyrje në retest; SL pas bishtit; TP te niveli fresh i radhës (ose RR 1:2 / 1:5).
4. Testi: 2026 + 10 vjet, orët 02/03/04, ekzekutim M1 (si laboratori i Opus), provë kundër rastësisë.

**Faza 2 — Trendline Breakout H1 (1 seancë)**: rregullat e librit fjalë për fjalë, i njëjti test.

**Faza 3 — ICT/QT (2 seanca)**: shkarkim i XAGUSD M1 2016–2025 (HistData) + 2026 nga cTrader; PSP = maja/fundi ku ari dhe argjendi mbyllin ndryshe (SSMT); çerekët 90-min dhe true open; target FVG (IRL) pas marrjes së ERL. MMXM s'kodohet i plotë (shumë subjektiv), vetëm pjesët e matshme.

**Faza 4 — integrimi**: vetëm ajo që kalon testin hyn në bot si modul më vete me çelës (`MSNR=true` etj., parazgjedhje off), me të njëjtat rregulla rreziku: 0.01 lot, 22:30, stop pas 2 humbjeve.

## Rregulli i pranimit (i njëjtë si gjithmonë)
Më shumë $ dhe DD jo më i madh në 2026 DHE 10 vjet, në të tria orët e fillimit, me ekzekutim M1, dhe mbi zhurmën e filtrave të rastit.
