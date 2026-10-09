# GDIS Loader v0.23 — полный audit report

## A. Verdict

**AUTOMATED PASS / NATIVE EXCEL PENDING / CANDIDATE.**
Structural v3 canonical=false. Native acceptance v2 (2026-10-07) не переносится на v3.
Дата сравнения до/после: **2026-10-09**, единый local system calculation date.
Baseline implementation: v0.22, commit `3490441a13d6c36849754a404d13b1933e41c0ed`.

## B. Root causes

- **10306:** Base содержит один initial completion, launch `12.2023`, canonical
  plast ПК17. Все семь valid Summary rows имеют explicit `_ЗБС`. Старый resolver
  требовал отдельный dated ЗБС event в Base, поэтому возвращал NO_GDI/count=0.
  Canonical plast уже совпадал: ПК-17-1→ПК17. Причина — lifecycle gate.
- **10405:** предположение про pre-launch **не подтверждено имеющимися файлами**.
  Launch `11.2014`→2014-11-01; первая valid строка 2015-02-03. Всего 8 valid
  rows и 2 Pст, которые не входят в authoritative список ГДИ. Старое=8, новое=8.
  Ни запись до запуска, ни «потерянная девятая» здесь не обнаружены.
- **Plast normalization:** reader audit не обнаружил разных canonicalizers:
  Summary, Base, LHA, status и fund scope используют normalize_plast. Старое
  расхождение count=0 при ПК17/ПК17-1 было следствием lifecycle gate. В v0.23
  один current_gdi_history обслуживает count/LND/depth/productivity/durations;
  Delta/LHA применяют тот же canonical plast и lifecycle resolver.
- **КСД:** отсутствовал в enum, classifier и valid-kind sets. `КВД+ИД` ранее
  попадал в KVD prefix и терял ID capability. Добавлены KSD/combined semantics.
- **Downhole:** service проверял depth только match.record.
- **ЛНД:** service проверял inputs только match.record; previous fallback отсутствовал.
- **Pre-launch:** temporal assignment и отдельный count cutoff повторно исключали
  current-branch rows. Теперь launch остаётся evidence; safe assignment выполнен один раз.

## C. Structural v3

Расходомер физически удалён из Данные/tblData, TargetRow, output schema и mapping.
Остальные retired inputs сохранены. App release target 0.23; template version 3.
Calculation/rating capacity **1000**; initial input table **100** styled rows,
расширяется writer до A6:Y1006 при 1000 строках. Auto calc/fullCalcOnLoad/forceFullCalc сохранены.

| Changed OOXML part | Exact operation |
|---|---|
| `xl/worksheets/sheet3.xml` | delete G cells; H:Z -> G:Y; corresponding dimensions, widths, merges and selection |
| `xl/tables/table2.xml` | delete named column; 26 -> 25; sequential IDs; refs A6:Y106 |
| `xl/sharedStrings.xml` | erase unused label at stable index 194; decrement total references by one |
| `xl/worksheets/sheet2.xml` | remove only Расходомер from B52 unused-input note |
| `xl/workbook.xml` | GDIS_TEMPLATE_VERSION 2 -> 3; calcPr unchanged |

Added/removed ZIP entries=0; **unexpected changes=0**. v2 неизменён.
Formula cell count: **147562 → 147562**.
Все formula sheets (Критерии, Расчет, Рейтинг), λ/rank, charts/series, styles,
relationships, calculation/rating tables и CF extensions byte-identical.
Defined names отличаются только template marker. Settings DV/protection неизменны;
data CF неизменён, data DV/protection отсутствуют в обоих. Перенос всех оставшихся
cells проверен с исходными style/value. Формулы не содержат direct Данные!G refs
или ссылок на имя удалённого поля; широкие INDEX/MATCH ranges сохранены и находят
колонки по headers. #REF!=0. calcChain отсутствует, вручную не добавлялся.

- v2 SHA-256: `645a3e5ba9303c42f441598e71fb7da261c9738789638cb5a0e7fceaf97d2578` (13705243 bytes).
- v3 SHA-256: `6a7523fdbf524fd9b7f6709d0b3b95279641c706f958c36d388a41c23d610248` (13705012 bytes).

Exact part hashes: `artifacts/v0.23/ooxml-diff.json`; preservation inventory:
`structural-proof.json`. Migration SHA-pinned; cross-platform gate compares OOXML
payloads, поскольку compression bytes могут различаться между zlib builds.

## D. Unified GDI reconciliation

1. Parse canonical well identity/root/family/ordinal; normalize field and exact plast.
2. Classify approved prefixes; preserve raw label and source cells.
3. Collapse exact business duplicates with combined provenance; distinct attributes retained.
4. Restrict valid dated Summary evidence to selected field/root and calculation cutoff.
5. Resolve confirmed Base/Fund current history. For initial-only Base, Summary may
   confirm its missing ЗБС marker **only** with one explicit ordinal-1 branch,
   matching Base canonical plast and compatible Fund scope; no conflicting markers,
   active rival branches, undated/different Base boundaries or interleaved root rows.
   Root rows must precede both the branch evidence and Base completion launch.
   Base launch/precision/provenance are preserved; observation date is not invented as launch.
   Conflicting evidence yields AMBIGUOUS, never arbitrary selection.
6. Within that history choose authoritative latest Summary plast. Equal latest dates
   with conflicting canonical plasts block assignment. Separate GS/MZS and ordinal branches remain separate.
7. `current_gdi_history` applies valid type/date, field/root, cutoff, canonical plast
   and common lifecycle resolver. Root-only rows follow confirmed timeline.
8. Launch disagreement is allowed only for a unique initial identity/plast with no
   other history, or an explicit unique ЗБС branch after its predecessor's confirmed
   start. Same-display later stages prevent an ambiguous early assignment. No day tolerance.
   Old/root rows cannot jump to post-ZBS, PVLG or PNLG. Status/LHA do not gain global pre-launch acceptance.
9. Count each reconciled deduplicated row once. Do not reapply `date>=launch`.
10. Same ordered current history supplies productivity, durations, depth window,
    latest/previous LND. Delta retains independent finite-value search and 730-day
    cutoff, same current lifecycle/plast; Delta values are never compared across dates.

No production well-number exceptions. Legacy GUI/CLI/config and numeric thresholds
remain intact. Writer accepts both old and v3 headers; verifies their actual positions,
including Manual μ beyond the first 25 columns in v1/v2. It changes only Данные/tblData.

## E. Research classifier

NFKC/trim/uppercase, separators normalize; approved prefix plus existing safe
explanatory suffixes. Combined checked before singleton prefix. No fuzzy matching.
KSD is a pressure study; it advances duration without pressure/KVD, without adding ID.

| Raw | Canonical | ID capability | Pressure capability | Count per row |
|---|---|---|---|---|
| КВД | KVD | no | yes | 1 |
| КСД | KSD | no | yes | 1 |
| ИД | ID | yes | no | 1 |
| ИД+КВД | ID_KVD | yes | yes | 1 |
| КВД+ИД | ID_KVD | yes | yes | 1 |
| Pст | EXCLUDED | no | no | 0 |
| ПГИ | UNKNOWN | no | no | 0 |

Existing `КВД+КСД` stays KVD (one row); other unknown/excluded labels remain unchanged.
Current production bundle has no standalone КСД or КВД+ИД counted rows; synthetic
classifier and service-duration tests cover both capabilities and one-row-one-count.

## F. Canonical plast

Existing normalize_plast contract preserved: Unicode normalization, spaces/dashes,
primary ПК numbers, ignore sublayer suffixes. ПК17=ПК17-1=ПК17-2=ПК17-2-1;
ПК19-20→ПК19+20; ПК14-1,ПК15-1→ПК14+15. Significant composite constituents remain:
ПК14≠ПК14+15, ПК17≠ПК18. No unrestricted suffix stripping or fuzzy matching.
Cross-feature test checks count, depth, LND previous and historical Delta for ПК17-1/-2.

## G. Downhole three-year rule

Inclusive `[calculation_date minus 3 calendar years, calculation_date]`, each record's
own date, current resolved history/plast only. Feb 29 clamps to Feb 28 in target year.
At 2026-10-09: 2023-10-09 included; 2023-10-08 excluded; future rows excluded.
Any finite parsed depth strictly >0 and >configured threshold (default 0) gives Да.
Numeric zero/negative, blank or invalid text never confirm. Invalid text gets
GDI_DEPTH_INVALID with exact file/sheet/cell. No qualifying row in resolved history
(with valid GDI, even if all older than the window) gives Нет. Unresolved/NO_GDI
keeps the established missing-data contract. Python truthiness is not used for numeric validity.

## H. LND fallback

Keep lnd_condition unchanged. Order valid current history by study timestamp,
source file, sheet and row. Use latest when its existing rule returns true **or false**.
Only when result is None, inspect immediate previous valid row. Do not search deeper
or replace an inconvenient false result. Zero in numeric RFP input remains valid.
Provenance records source cells and latest/previous. Foreign histories/plasts excluded before selection.

## I. 10306 — complete reconciliation

Source `Сводная таблица ГДИ.xlsx`, sheet `ГДИС_Сибнефтегаз в целом`.
All rows: raw/canonical well `10306_ЗБС`, raw plast `ПК-17-1`, canonical `ПК17`.
Selected current identity `10306_ЗБС`; Base launch **2023-12-01** (MONTH precision),
Summary confirms missing marker. No root/other branch source rows found.
Old count **0**, new **7**, established from source rows, not hardcoded runtime.

| Source row | Date | Raw type | Canonical | Launch relation | Counted | Reason | Depth feature source | LND source |
|---|---|---|---|---|---|---|---|---|
| 1557 | 2023-12-04 | ИД+КВД освоение | ID_KVD | after | yes | current identity/history/plast | no | — |
| 1558 | 2024-01-17 | ИД+КВД | ID_KVD | after | yes | current identity/history/plast | yes | — |
| 1559 | 2024-04-13 | КВД статика | KVD | after | yes | current identity/history/plast | no | — |
| 1560 | 2024-05-28 | ИД+КВД | ID_KVD | after | yes | current identity/history/plast | yes | — |
| 1561 | 2024-09-08 | ИД+КВД | ID_KVD | after | yes | current identity/history/plast | no | — |
| 1562 | 2025-06-05 | КВД при ПГИ | KVD | after | yes | current identity/history/plast | yes | previous |
| 1563 | 2025-09-18 | КВД+КСД | KVD | after | yes | current identity/history/plast | yes | — |

Last row has unrecognized LND reliability, so previous row 1562 supplies the unchanged
LND rule. Depth uses rows in the three-year window, not just row 1563.
Full per-row fields/diagnostic codes: `controls-reconciliation.json` in local bundle.

## J. 10405 — complete reconciliation

Same source/sheet. All rows: raw/canonical well `10405`, raw plast `ПК-19-1+2`,
canonical `ПК19`; selected current initial history. Base launch **2014-11-01**.
Old **8**, new **8**. No formerly pre-launch-excluded record exists in this bundle.
The 2 Pст rows remain excluded under the authoritative classifier.

| Source row | Date | Raw type | Canonical | Launch relation | Counted | Reason | Depth feature source | LND source |
|---|---|---|---|---|---|---|---|---|
| 1604 | 2015-02-03 | ИД+КВД | ID_KVD | after | yes | current identity/history/plast | no | — |
| 1605 | 2019-10-29 | КВД | KVD | after | yes | current identity/history/plast | no | — |
| 1606 | 2019-11-17 | ИД+КВД | ID_KVD | after | yes | current identity/history/plast | no | — |
| 1607 | 2022-06-05 | КВД статика | KVD | after | yes | current identity/history/plast | no | — |
| 1608 | 2022-09-27 | КВД+КСД | KVD | after | yes | current identity/history/plast | no | — |
| 1609 | 2023-10-04 | ИД+КВД освоение | ID_KVD | after | yes | current identity/history/plast | no | — |
| 1610 | 2023-10-27 | КВД статика | KVD | after | yes | current identity/history/plast | no | — |
| 1611 | 2024-04-04 | КВД статика | KVD | after | yes | current identity/history/plast | no | latest |
| 1612 | 2025-08-27 | Pст | EXCLUDED | after | no | INVALID_TYPE | no | — |
| 1613 | 2026-07-12 | Pст | EXCLUDED | after | no | INVALID_TYPE | no | — |

For a different production file containing a ninth valid study, rerun the same
reconciliation; do not manufacture count=9. General pre-launch cases are covered
synthetically and restore 18 real current-branch rows across other wells.

## K. Production field summary — before → after

Exact current source files, same calculation date; v0.22 baseline vs v0.23.
Baseline calculator v1 vs v3 affects formula packaging, not source-derived comparisons.
All outputs are private; output counts are cross-checked against reconciliation records.

| Field | Eligible | MATCHED | AMBIGUOUS | NO_GDI | INVALID_SOURCE | Total GDI | Wells with changed count |
|---|---|---|---|---|---|---|---|
| Береговое | 78→78 | 77→78 | 0→0 | 1→0 | 0→0 | 796→819 | 12 |
| Пырейное | 5→5 | 5→5 | 0→0 | 0→0 | 0→0 | 23→23 | 0 |
| Хадырьяхинское | 10→10 | 9→9 | 0→0 | 1→1 | 0→0 | 55→57 | 2 |

| Field | Restored plast | Restored lifecycle | Former pre-launch now counted | КСД | КВД+ИД | Downhole Да | LND previous fallback |
|---|---|---|---|---|---|---|---|
| Береговое | 0 | 7 | 16 | 0 | 0 | 19→34 | 23 |
| Пырейное | 0 | 0 | 0 | 0 | 0 | 2→2 | 1 |
| Хадырьяхинское | 0 | 0 | 2 | 0 | 0 | 1→9 | 2 |

Restored plast=0 because existing canonicalization was already correct. No phantom
normalization recovery is attributed to lifecycle changes. Береговое old count=20
for well12 becomes21 under the new unique-history launch-evidence rule; 13/21/22
stay21/19/19. 12 known daily field ambiguities persist with blank Debit; no assignments guessed.

## L. Tests

Baseline **516**, current **569** (+53); no test removed. New tests cover all approved
types/capabilities, combined count, suffixes, unknown labels, depth boundaries/leap
calendar, latest-zero/blank, foreign histories/plasts, LND no-deeper-than-previous,
zero, deterministic ties, unique/conflicting Summary branches, Base launch retention,
safe pre-launch and true old-history rejection, cross-feature plast and Delta, v3
exact OOXML/payload/cell preservation, schema and 1000-row writer, candidate release gate.
Production regressions pin all 10306/10405 included/excluded source rows and run all
three fields with structural v3. Legacy writer is still tested with v1/v2.

Actual before-fix reproduction: v0.22 production 10306=0, summary rows valid;
old downhole/latest and blank LND behavior captured in baseline reports. Existing
research classifier had no KSD and classified reverse combined as KVD. Old count
excluded 16/0/2 current-branch pre-launch rows. Retired expectations updated only
where the new customer contract changes their meaning; gates are not weakened.

Final local `uv sync --locked` and `make check`: PASS; **569 passed** in 433.49s.
Ruff, formatting and ty PASS. Machine evidence: quality-summary.json.
One openpyxl unsupported-CF-extension inspection warning is expected from existing
v2 read inspection; no openpyxl save is used for structural migration or runtime writing.

## M. CI/build

Windows standalone onedir packaging unchanged. Frozen smoke requires exact injected
0.23. Release now depends on successful Linux make-check and Windows build/checks.
Existing CI matrix independently runs Linux and Windows. Remote run URLs, conclusions
and frozen-build evidence are recorded in release-evidence.json after completion.
Production workbooks are absent in CI and their six tests auto-skip there.

## N. Native Excel

**PENDING**; Microsoft Excel is unavailable in this Linux environment. No claimed
repair-free open, native calculation, save/reopen or native λ/rank PASS for v3.
Review includes synthetic Golden_v3_NATIVE_PENDING.xlsx and the 11-point checklist
with version/hash recording. v3 remains canonical=false. v2 native PASS preserved.

## O. Release

App target **0.23**, structural **3**, previous accepted structural **2**.
Source/dev fallback remains 0.1 by existing build-version injection policy; no
version-bump commit. Main push computes next global monotone tag and tags exact
successfully built SHA. Candidate metadata yields GitHub **prerelease**, never
canonical promotion. Manual dispatch remains non-release/no-tag.
Exact release commit, tag, URL, assets/digests and clean Git status are recorded in
release-evidence.json and final local audit report. Do not publish/tag on automated failure.

## P. Residual risks / review bundle

- New native Microsoft Excel acceptance is still required for physical v3 migration.
- Existing daily source lacks safe field assignment for 12 target wells; debit remains blank.
- Supplied 10405 evidence supports8, not9; a different customer source would require fresh audit.
- Missing/contradictory branch evidence remains unresolved; Summary inference deliberately
  limited to one agreed Base completion. No invented boundary/ordinal or fuzzy plast selection.

Local review ZIP: `artifacts/v0.23/GDIS_v0.23_review.zip` with report, summary,
exact OOXML part hashes, v2/v3 hashes, tests, production aggregates, minimal control
rows, classifier/plast evidence, native checklist/golden and release evidence.
No production source books, filled output books, full row dumps or logs are bundled.
