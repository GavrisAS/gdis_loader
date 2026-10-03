# Historical pre-migration: Structural audit before migration — accepted v0.19

Canonical input: `data/GDIS_Rating_Calculator_FIXED.xlsx`; no repository-stored template or canonical pointer exists. Size: 1886651 bytes.
SHA-256: `bb046cc365749a546d1bbe141165b08a664ba427ab9493b678ddce008fc85c6a`.

Byte-identical backup: `artifacts/calculator/archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx`. Artifacts are local only; production workbooks are not added to Git.

Complete cell-level formula inventory, caches presence, XML relationships, tables, chart series, names, formatting, validation, hidden dimensions, print settings, freeze panes and extensions: `artifacts/calculator/audit-pre.json`. Source data values are excluded.

Dependency graph: Данные → Критерии (raw INDEX/MATCH helpers AG:BJ / BL:CO; μ B:AE) ← Настройки (30 slots A21:U50). Критерии → Расчет (counts, weights, λ, rank, status) → Рейтинг → chart1 (Рейтинг K21:L50). README explains settings. Four tables: tblCriteria, tblData, tblCalculation, tblRating. No defined names, external links, custom XML, pivots or macros. One chart and drawing; calcChain present. x14 conditional-formatting and x14ac extensions must survive.

## Current mathematics

Let w_i = Настройки D(21+i), μ_i = Критерии column (B+i), numeric membership n_i = ISNUMBER(μ_i). H = Σ n_i w_i. Current λ = exp(Σ n_i w_i ln(μ_i) / H), but blank if well absent, H=0, or ANY μ is “Недостаточно данных”, “Поле не найдено”, “Некорректные настройки”. This is weighted geometric aggregation, not multiplication of raw μ.

YES_NO uses I/J settings (default Да=1, Нет=0.1); sigmoid uses R + (S−R)/(1+exp(−H*(raw−G))), floored at B14=1e−9. Active rows 21:29 include obsolete ADD row28. Remaining active weights after removal sum to 0.95; normalization is already implicit in H. B18 incorrectly assumes sum=1 even though λ divides by H.

Ranking: Расчет K = count of strictly greater λ + running count of equal λ, so deterministic source-order ties. Blank λ has blank rank. Рейтинг uses INDEX/MATCH over K. Unranked wells appear only in Расчет, not ranked list. Chart is final λ only; 30 source rows and TOP-N selection.

## Capacity and compatibility

Критерии rows20:119, Расчет/Рейтинг rows4:103 cover 100 wells. Raw INDEX/MATCH ranges hardcode Данные A7:CV106 and headers A6:CV6; table contractions do not remove formula rows. Future expansion needs a template-only capacity change. Current functions are legacy IF/INDEX/MATCH/COUNTIF/EXP/LN; no modern dynamic arrays. Minimum tested Office version is unknown; retain legacy function set.

Critical raw helper issue: INDEX of blank source can return numeric zero. Preserve blanks explicitly before μ evaluation. Numeric source zero must remain valid.

Manual μ has no configured criterion: available generic MANUAL_MU branch, no active use, no override of λ. Preserve input column; do not activate it.

## Sheets

- README: 36 rows × 8 columns; state=visible; tables=[]; CF=0, DV=0, merged=A1:H2 A4:H4, freeze=None.
- Настройки: 50 rows × 21 columns; state=visible; tables=[('tblCriteria', 'A20:U50')]; CF=2, DV=7, merged=A1:M2 A3:D3 A19:U19, freeze=None.
- Данные: 106 rows × 26 columns; state=visible; tables=[('tblData', 'A6:Z106')]; CF=1, DV=0, merged=A1:Z2 A4:Z4, freeze=None.
- Критерии: 119 rows × 93 columns; state=visible; tables=[]; CF=1, DV=0, merged=A1:Q1 B2:Q2 AG2:BJ2 BL2:CO2, freeze=None.
- Расчет: 103 rows × 14 columns; state=visible; tables=[('tblCalculation', 'A3:N103')]; CF=2, DV=0, merged=A1:L2, freeze=None.
- Рейтинг: 103 rows × 12 columns; state=visible; tables=[('tblRating', 'A3:I103')]; CF=2, DV=0, merged=A1:I2, freeze=None.

Final durable assets now live in tracked templates/calculator; this inventory describes the original baseline only.
