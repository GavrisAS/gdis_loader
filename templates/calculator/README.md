# Calculator assets — v0.24 loader candidate

Structural v3 removes only «Расходомер» from Данные/tblData (25 columns).
Capacity remains 1000 in calculation/rating tables. Formulas, λ/rank, charts,
styles, protection, criteria participation and auto-recalculation are preserved.
Runtime changes only Данные/tblData in a new output workbook.

Status: **AUTOMATED PASS / NATIVE EXCEL PENDING / CANDIDATE**, canonical=false.
Microsoft Excel acceptance is required before v3 becomes canonical.
Structural v3 itself is unchanged for v0.24. Debit source qualification is in
docs/AUDIT_v0.24_RELEASE.md; native Excel acceptance remains pending.
See docs/CALCULATOR_NATIVE_EXCEL_SMOKE.md and historical docs/AUDIT_v0.23.md.

Previous accepted v2 is retained byte-for-byte; its native Microsoft Excel PASS
was confirmed by the user on 2026-10-07. Archive v1 is retained for rollback.
No acceptance of v2 is claimed as acceptance of v3.

Delivery: v3 candidate, accepted v2, archive v1, SHA256SUMS.txt and version metadata
are separate release assets alongside the Windows standalone folder ZIP.
No Python is required on the target PC. Select the desired workbook via Обзор.
SHA256SUMS.txt uses repository-root paths; downloaded files can be checked by
basename with Get-FileHash -Algorithm SHA256. Sources/output workbooks are not assets.
