# Native Excel acceptance — structural v3 PENDING

Current candidate: `templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v3.xlsx`.
Loader target: v0.23. Status: AUTOMATED PASS / NATIVE EXCEL PENDING / CANDIDATE;
canonical=false. Accepted structural v2 has native PASS confirmed 2026-10-07.
That historical acceptance does not cover the changed v3 workbook.

Run the Windows loader against v3 and each local production field. Keep source
workbooks and filled production outputs private. The local review bundle includes
minimal reconciliation evidence and matching synthetic v2/v3 golden workbooks.
Compare λ/rank in Golden_v2_REFERENCE.xlsx and Golden_v3_NATIVE_PENDING.xlsx
for identical inputs; all_unknown must yield blank λ/rank in both.

| Microsoft Excel check | Result |
|---|---|
| Open original v3 and updated v3 without repair warning | PENDING |
| Recalculate automatically on open, without F9 | PENDING |
| λ and rank match expected controlled examples | PENDING |
| Editable settings changes trigger automatic recalculation | PENDING |
| Charts display and series remain correct | PENDING |
| Formatting and conditional formatting intact | PENDING |
| Protection locks intended cells, editable settings remain editable | PENDING |
| Расходомер absent, other retained columns present | PENDING |
| Writer values land under correct named headers | PENDING |
| No #REF!, #VALUE!, unexpected #N/A | PENDING |
| Save, close and reopen preserve workbook behavior | PENDING |

Record operator, date, Excel version, template/output SHA-256 and results for all
checks. Inspect chart intentional #N/A separately from unexpected errors. Save
native outputs locally and rescan with `scripts/scan_excel_smoke.py`. Only an
explicit confirmed native PASS permits canonical=true and candidate promotion.
No Microsoft Excel is available in this Linux development environment.
