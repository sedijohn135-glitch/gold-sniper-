# Setup-et e pronarit (analizat reale) dhe çfarë bën boti me to

Çdo setup që më ke mësuar, i shënuar me rregullat, kodin dhe rezultatin në 8 muaj
(M5 nga llogaria, 26 janar – 25 shtator 2026). "Live" = boti e tregton vetë në Railway.

| # | Setup-i yt | Kodi | 8 muaj | Statusi |
|---|---|---|---|---|
| 1 | **H1 supply + M5 Quasimodo (HH/LL) + divergjencë AO**. Hyrje me rejection M5 te left shoulder, SL mbi rejection, TP demand M15 poshtë | `research/quasimodo.py` | 109 trade, +20.8R (me AO vetëm 7–8 trade) | kërkim; i kap 25 shtatorin (SELL +5.7R, BUY +3.3R) |
| 2 | **H4 support + divergjencë AO M30 + QM M15 që thyen majën**. Kthim te QM, rejection M5, hyrje në mbyllje, SL nën wick, TP supply M5 i pamitiguar | `research/quasimodo_mtf.py` | 16 trade, −6.3R | kërkim |
| 3 | **Trendline 3rd touch M30 + thyerja e supply-t më të afërt M30**. Retest me rejection M30, hyrje në mbyllje, SL nën supply-in e thyer, TP supply M30 fresh lart | `research/trendline3.py` | 6–16 trade, 0 deri +6R | kërkim (shumë i rrallë) |
| 4 | **H1 supply + demand M1 i thyer → supply M5 fresh**. Retest në të njëjtin nivel, rejection M5 me wick, sell menjëherë, TP te prekja e 3-të e trendline-it | `bot/confluence.py` (≥ 4 nivele fresh) | 64 trade, +23.3R | **live** (`GoldSniper-C`) |
| 5 | **Pse H1/H4:** nëse çmimi s'e thyen dot murin H1/H4, tregu s'ka forcë. Pastaj konfirmimet: zonë M5 e thyer, QM, trendline, divergjencë AO | `bot/hierarchy.py` (muri H1 + thyerje strukture M5 + AO) | 233 trade, +95.6R, DD 14.8R | **live** (`GoldSniper-H`) |
| 6 | **H4 support i fortë + divergjencë AO H1 + thyerja e supply-t M15 më të afërt**. Retest me wick në M15 → hyrje, SL nën qirin e rejection-it, TP1/TP2 supply D1, TP3 supply-i dominant lart | `research/swing.py` | 41 trade, 5 fitime, +34.7R (pa 4 gushtin −21R) | kërkim; kap 4 gushtin saktë |

## Shembulli 6 në detaje (4 gusht 2026)

- **H4:** demand 4020–4035, i mbajtur që nga 24 korriku (asnjë mbyllje H4 poshtë).
- **H1:** low 4019.14 (3 gusht 13:30 UTC), më i ulët se low-i i 31 korrikut, ndërsa AO bën low më të lartë.
- **M15:** zona 4045.51–4049.81 u thye dy herë. Ishte demand, u bë supply, pastaj u thye përsëri lart (19:15 UTC).
- **Hyrja:** qiri M15 i 01:00 UTC (O 4048.88, H 4050.65, L 4042.61, C 4046.94). Wick-u kaloi poshtë zonës dhe qiri u mbyll brenda saj. BUY në 4047.14, SL 4042.11.
- **TP:** 4117/4154 (+14 deri +21R, 5 gusht), 4315–4328 (+56R, 7 gusht), 4430 (+76R, 11 gusht),
  **4689 = supply-i dominant (+128R, 25 gusht)**. Çmimi s'ra më nën 4045.60.

**Pse s'është live:** të njëjtat rregulla shfaqen edhe 40 herë të tjera në 8 muaj dhe
aty humbin. Ajo që e bën 4 gushtin të veçantë (p.sh. kaq javë range mbi support-in H4)
ende s'është kthyer në rregull. Shkurt–maji humb në çdo variant.

## Çfarë mësova nga të gjitha

- **Muri i kohës së lartë + divergjenca AO** është konfirmimi që funksionon më mirë (modulet 4 dhe 5).
- **Zona e thyer (flip)** ka avantazh, sidomos kur zona thyhet disa herë.
- QM dhe trendline-i si konfirmim i vetëm s'dolën fitimprurës në kod.
- Fitimi vjen gjithmonë nga pak trade të mëdha: SL i vogël pas wick-ut, TP te nivelet e kohës së lartë.
