# GDIS Loader v0.24 production qualification

## Verdict and scope

**PASS for debit calculation on Beregovoe using the September 2026 report.**
The calculation ran with `calculation_date=2026-10-12` and the default
`gas_rate_working_day_min_rate=0.0`. Pyreinoe and Khadyr'yakhinskoye were not
run: the attached report contains Beregovoe daily sheets only. Structural v3
remains non-canonical pending native Excel acceptance.

The full private row-by-row before/after audit is generated locally at
`artifacts/v0.24/AUDIT_v0.24_FINAL.md`; its paired CSV and JSON retain source
coordinates and candidate evidence. Those production rows and source workbooks
are not included in this review bundle.

## Source inventory

The input is `data/09.2026 Cуточный рапорт БГП.xlsm`, SHA-256
`56fb8f826fe70671ebc0a69bb5fc80c62ef63a64f1cbab30e7d3530e996151b3`, 10,994,783
bytes. The unique normalized match for the authoritative tab is
`Добыча телеметрия`. It spans `A1:AH122`; row 1 contains `ГСК`, `СКВ.`, and
day labels 1–31. `ГСК` is a gas-collector identifier, not a field label. The
dated daily tabs `01`–`30` are September 1–30, 2026; tab `31` has no date and
was excluded. The telemetry tab has 3,839 formulas, no blank cached formula
values, and 16 merged ranges. The daily tabs contain merged header/section
cells. The report provides no `БЛУ`/`ПЛУ`/`ХЛУ` section markers.

Each dated daily tab has the exact title `БЕРЕГОВОЙ (ОПОРНЫЙ) ГАЗОВЫЙ ПРОМЫСЕЛ`
at `A1`, its date at `A4`, the well identity in column D, and daily gas rate in
`AH` (header `AH7`, `тыс.м³`). The telemetry row's day formula must directly
reference the corresponding `AH` cell on the sheet for that day, and the
referenced `D` row must normalize to the telemetry well. This ties the row to
the report's field, date, and well without inferring scope from collector IDs,
row order, colors, or another field's same-numbered well.

## Root cause and matching rule

The previous reader treated column `ГСК` as a field name. In September it
contains blanks or collector numbers; it does not identify the oil/gas field.
As a result, valid Beregovoe records lost field scope and matches became
`DEBIT_SOURCE_FIELD_AMBIGUOUS` when the fund contained the same physical well
root under multiple fields.

The reader now verifies the dated sheet title, date/day agreement, direct
formula destination, and normalized well identity on every day in the report
month before assigning field scope. It filters to the selected field before
resolving candidates. Physical root and target lifecycle identity remain
separate: `71_ЗБС` and `113_ЗБС` resolve to source rows 32 and 31 (raw IDs 71
and 113), while their current target identities remain suffixed. An unproven
day link, unknown field marker, row-identity mismatch, or unresolved lifecycle
does not assign a debit. No debit formula or threshold semantics changed.

The fail-safe is observable in the report: telemetry `B108` identifies well
`10703`, while `AF108` points to `30!AH114`; that daily row identifies `Р-83`
at `30!D114` (and `30!AB114` is `=D114`). Because the target well does not
match, the row remains field-unproven and cannot supply a debit.

## September results

The v0.23 baseline and v0.24 run use the same bytes for every input,
`calculation_date`, and criteria snapshot. The v0.23 baseline was executed
against the September report; it is not the July historical result.

| Metric | v0.23 baseline | v0.24 |
|---|---:|---:|
| Eligible Beregovoe rows | 78 | 78 |
| Filled debit | 63 | 75 |
| Blank debit | 15 | 3 |
| Ambiguous resolved | — | 12 |
| Still ambiguous | 12 | 0 |
| No valid working days | 3 | 3 |
| Missing/unproven source | 0 | 0 |
| Other blank reason | 0 | 0 |

The 12 prior ambiguous rows each had one consistent, field-proven Beregovoe
candidate with 30 valid positive days. Their arithmetic means now populate the
debit. All 63 previously filled debit values remain unchanged within numeric
tolerance; every non-debit output field is unchanged. The 3 remaining blanks
have field- and well-proven September rows, but no numeric daily value strictly
above zero across the 30-day period. They remain blank with
`DEBIT_NO_VALID_WORKING_DAYS`; no zero was substituted.

The exact identities, target rows, candidate telemetry rows, daily sheet and
cell coordinates, old/new diagnostics, valid-day counts, lifecycle evidence,
decisions, and reasons are in the ignored local reconciliation JSON/CSV. These
include the full 78-row before/after comparison and all 15 baseline blanks.
The 12 historical July control identities were also present among the
September unresolved set and are resolved there; the July workbook itself is
not in `data/`, so no July production rerun is claimed.

## Calculation, tests, and preservation

An independent audit compared all 2,340 daily telemetry cached values for the
78 eligible candidates against their linked `01`–`30!AH` values. Selected
debits equal the arithmetic mean of numeric rates strictly above the existing
threshold. Synthetic tests cover cross-field same-number selection, inherited
section scope, unknown scope, leading zero normalization, lifecycle suffix,
formula-cache missing behavior, date/identity mismatch, and row-order safety.
The complete suite passes **581 tests** (569 before this fix; 12 new tests).

Structural v3 SHA-256 remains
`6a7523fdbf524fd9b7f6709d0b3b95279641c706f958c36d388a41c23d610248`; v2 and
rollback templates are unchanged. The output writer changed only
`xl/worksheets/sheet3.xml` and `xl/tables/table2.xml`. Capacity remains 1,000,
and formulas, tables, charts, formatting, protection, and recalculation
settings are preserved. `canonical=false` remains in effect.

The exact hashes for all inputs, effective criteria, output ZIP-part comparison,
source inventory, and row-level audit are retained under ignored
`artifacts/v0.24/`. The release workflow will create the two-component v0.24
tag and Windows release only after the Linux checks, Windows build, and frozen
smoke test pass. It packages no production source workbooks.
