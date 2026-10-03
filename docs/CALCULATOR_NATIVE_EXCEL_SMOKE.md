# Native Excel acceptance — PENDING

This Linux environment has no installed Microsoft Excel for Windows. Automated
formula evaluation does not replace this gate. Canonical switch is prohibited
until an operator records actual results against the exact metadata SHA.

Use Microsoft Excel on Windows and the same loader release (expected v0.21).
Verify SHA256SUMS before opening. Keep templates and production sources unchanged.

For Береговое, Пырейное, Хадырьяхинское:
1. Select tracked v2 template and existing source files; run update with explicit field.
2. Open output in Excel. Record Office version and absence of repair/unreadable
   content/removed-records warnings. Any such warning is FAIL.
3. Ctrl+Alt+F9 (full calculation), then save a separate `SMOKE_<field>.xlsx`.
4. Inspect λ/rank, tables, charts and conditional formatting. Inspect Настройки:
   B12/L21:L50 have no dropdown and reject editing; B5, B6, B7, B8, B9, B10, B11, B16 and D21 are each edited and
   restored successfully; obsolete rows hidden and B52 lists unused criteria; Manual μ unused.
5. Scan every worksheet's cached error cells after save using:
   `uv run python scripts/scan_excel_smoke.py SMOKE_<field>.xlsx`.
   Unexpected #REF!, #VALUE!, #DIV/0!, #NAME?, #NUM!, #N/A must be zero.
   An intentional chart #N/A requires exact cell and documented reason.

Golden scenarios in a separate synthetic copy (never alter source workbooks):
run `uv run python scripts/prepare_excel_golden.py templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx Golden.xlsx`. This creates seven controlled rows with unique well ids.
All known, one unknown, multiple unknown, one known with positive weight must
produce numeric λ. All unknown must produce blank λ/rank. Да and Нет must each
participate according to normal μ semantics. Save after full calculation and
record cells and observed scores, not just a global checkbox. Automated golden
formula tests provide expected weighted geometric results.

Rollback: select tracked archive with the same loader, run one update, confirm
capacity=100 and only Данные/tblData changed. For 101 controlled rows expect
capacity warning. Never modify/archive-save the original rollback binary.

Record per field: input SHA, output SHA, Excel version, timestamp, operator,
repair warning absent, recalc performed, errors scan, λ/rank visible, charts/CF
rendered. Record golden scenarios individually. Attach smoke copies privately;
do not put production rows in the public review bundle.

Current results for all three fields and golden scenarios: NOT EXECUTED.
Native acceptance: PENDING. Overall: AUTOMATED PASS / NATIVE EXCEL PENDING
only when automated acceptance report confirms its own gates.

Settings UX: individually attempt B12, L21, L50 edits: Excel must reject each.
Retired rows28/34 remain hidden and all their cells locked. All field, UX,
golden and rollback native checks are PENDING; no Excel process is installed
or accessible in this Linux session. No native result has been inferred.

Field | Repair warning | Full recalc | Formula errors | λ/rank | Charts/tables/format/CF | Settings UX
---|---|---|---|---|---|---
Береговое | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING
Пырейное | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING
Хадырьяхинское | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING

Native golden results: all known PENDING; one unknown PENDING; several unknown
PENDING; one known PENDING; all unknown PENDING; Да PENDING; Нет PENDING.
Native rollback opens without repair: PENDING. Native error scan (including
intentional chart #N/A assessment): PENDING. Automated formula text integrity
and golden evaluator PASS do not demonstrate native Excel recalculation.
