# Structural v2 migration diff

Baseline: accepted loader v0.19 / `934c005100ac8289957e816cba2f8a2b55914152`.
The migration is offline; `run_update` and `excel.writer` do not invoke it.
Loader read-only compatibility changes target normal release v0.20; business thresholds unchanged.

The full cell-level old formula → new formula map is generated locally in
`artifacts/calculator/final/formula-map.json` (also included in review ZIP). It contains formulas, not production
input values. Pre-migration inventory: `artifacts/calculator/audit-pre.json`.

Entry | Expected change / reason
---|---
`xl/worksheets/sheet2.xml` | Clear obsolete slots28/34 including names, fields, codes and weights; disable them. Fix missing policy to exclusion; remove B12/L21:L50 validations, neutral locked cells, protect sheet, hide retired rows28/34, add unused notice at B52. Weight check accepts positive total because aggregation normalizes it.
`xl/worksheets/sheet4.xml` | Unknown μ becomes numeric0. Preserve raw blanks before INDEX returns0. Add hidden participation masks CQ:DT. Remove raw and μ expressions from obsolete slots. Preallocate1000 rows, extend absolute source ranges to row1006, retain existing transformations and extensions.
`xl/worksheets/sheet5.xml` | E/F count participation; G/N gate grounds/reasons with masks (even at thresholdμ=0); H sums participating weights; J aggregates only participating μ. Add hidden O ordering key so unknown-only wells remain visible after numeric scores. Preallocate1000 rows and extend ranking ranges.
`xl/worksheets/sheet6.xml` | Add hidden M lookup by ordering key. A shows rank only for ranked wells; B:I display unknown-only wells as well. Preallocate1000 rows. Chart helper ranges unchanged (first30 ranked results).
`xl/tables/table3.xml` | Extend tblCalculation to row1003. O is an auxiliary column outside the table.
`xl/tables/table4.xml` | Extend tblRating to row1003. M is auxiliary, outside the table.
`xl/styles.xml` | Explicitly unlock existing yellow input styles; fixed-policy cells use locked neutral style0 under sheet protection.
`xl/workbook.xml` | Add literal GDIS_TEMPLATE_VERSION=2; explicit automatic full recalculation on load and forceFullCalc.
`xl/calcChain.xml` | Remove obsolete calculation chain; Excel rebuilds dependencies on full recalculation.
`xl/_rels/workbook.xml.rels` | Remove only calcChain relationship.
`[Content_Types].xml` | Remove only calcChain content type.

Unexpected changed parts must be **zero**; this exact eleven-entry allowlist is
checked by migration and tests. The only removed ZIP entry is calcChain.
All other entries retain identical uncompressed bytes and their ZipInfo.

Unchanged: `Данные` worksheet, all26 headers, tblData definition, README sheet,
shared strings, theme, chart XML, drawing XML, remaining relationships,
properties and all unsupported extensions in unaffected parts. No workbook
round-trip, Excel automation or LibreOffice is used.

## Formula mapping by region

Region | Old | New | Reason
---|---|---|---
Настройки row28/34 | ADD/technical criterion definitions | Disabled empty slots, weight0 | Remove obsolete model inputs without shifting30-slot layout
Настройки L/T and B12 | Configurable missing policies / BLOCK | Exclusion / IGNORE | Missing semantics is fixed by customer decision
Настройки B18 | Sum weights≈1 | Positive total | Remaining default total=.95; H normalizes automatically
Критерии B:AE, rows20:1019 | Missing returns policy text/lowμ | Missing returns0; known transformation preserved | μunknown=0
Критерии AG:BJ / BL:CO | INDEX raw cell | IF(INDEX="","",INDEX) | Preserve blank; numeric0 remains numeric
Критерии CQ:DT | Absent | Explicit enabled + raw-valid + numeric-μ mask | Distinguish unknown0 from known criterion
Расчет E/F | COUNT(numericμ) / D−COUNT | Sum masks / D−E | Numeric unknown0 must not count as known
Расчет G/N | ISNUMBER / μ threshold without participation | Mask plus μ threshold, obsolete terms removed | Unknown0 never becomes an основание even when threshold=0
Расчет H | Σ ISNUMBER(μ)·w | Σ active·w | Exclude unknown from denominator
Расчет J | Missing sentinel blocks whole λ | Missing masks only their criterion; invalid settings still block | Preserve geometric scoring
Расчет O | Absent | Existing rank, else count numeric scores + running unknown count | Keep unknown wells without rank1
Рейтинг M / A:I | MATCH(rank), hide all unranked | MATCH(order key), blank displayed rank for unknown | Keep rows visible
Formula/formatting/table capacity |100 rows |1000 rows | Offline preallocation; runtime still writes only Данные

Geometric log operands use `MAX(Настройки!$B$14, μ)` when participating. Existing
sigmoid/manual floors remain. A configured known μ=0 participates as the
existing minimum μ rather than causing LN(0); unknown0 has mask0. A zero raw
numeric input participates and is transformed normally.

Legacy COUNTIFS, COUNTA, MATCH, INDEX, IF, EXP, LN are used; no LET/FILTER or
modern array functions. A specific minimum installed Office version cannot be
inferred from fileVersion alone. Target Office compatibility needs deployment
verification; the function ecosystem remains the same as baseline.


## Inferred Office compatibility

Full preservation of existing x14 conditional formatting implies Office2010+
(the baseline already contains that namespace); this is a structural inference,
not a claim that customer machines were checked. Microsoft's
[ConditionalFormatting schema documentation](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.office2010.excel.conditionalformatting)
identifies the extension as Office2010+. No newer function is introduced.
The actual customer Office version remains unknown.

Removing calcChain is safe for dependency reconstruction: Microsoft documents
that the chain can be rebuilt from formulas at load time in
[Working with the calculation chain](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-calculation-chain).
Automatic full recalculation is explicitly enabled; cached results are not proof.
