# Current acceptance — structural v3 / loader v0.23

v3: AUTOMATED PASS / NATIVE EXCEL PENDING / CANDIDATE, canonical=false.
New physical column deletion requires independent Microsoft Excel acceptance.
Current evidence: AUDIT_v0.23.md; checklist: CALCULATOR_NATIVE_EXCEL_SMOKE.md.
The accepted v2 and its historical evidence below remain unchanged.

# Acceptance update — v0.22

The user confirmed native Microsoft Excel acceptance of the exact v0.21 structural
v2 template in the v0.22 task on 2026-10-07: sheets, formulas, λ/rank and automatic
recalculation work. SHA-256 remains 645a3e5ba9303c42f441598e71fb7da261c9738789638cb5a0e7fceaf97d2578.
Template version2 is canonical and accepted; no new native acceptance is required
for the byte-identical v0.22 delivery. The historical pre-acceptance audit below
retains its original PENDING observations for traceability; this update supersedes them.

# Structural template v2 acceptance

Automated structural acceptance: **PASS**.
Overall: **AUTOMATED PASS / NATIVE EXCEL PENDING**.
`uv sync --locked` and `make check`: PASS, Python3.14.7; 500 tests passed.
Native Excel acceptance: **PENDING — NOT EXECUTED**.
Canonical status: **candidate**. Native Excel is a mandatory independent gate.

Windows delivery: option B, separate v0.21 Release assets; also tracked in Git.
Exact sizes/hashes and source baseline: CALCULATOR_TEMPLATE_VERSION.toml.
Rollback is byte-identical to the pinned original; never modified.

Formula model remains weighted geometric mean with active mask, minimum μ floor
and participating-weight denominator. Zero denominator produces blank λ/rank.
Unknown excluded; known Нет participates. Obsolete criteria excluded; Manual μ
unused. Input table retains all26 headers; formula capacity1000.

Runtime capabilities read calculation/rating tables without edits. Old100,
v2 1000; explicit unknown capacity for unsupported structure. Boundary tests
cover 100/101 for old and 100/101/1000/1001 for v2, including writer warnings.
Old/unknown missing exclusion limitation is reported; v2 has no stale warning.

UI: B12 and L21:L50 dropdowns removed, locked neutral policy cells with sheet
protection. Explicit B5:B11 and B16 unlocked with visually identical clones; active criterion
settings including D21 unlocked. No fill-based unlocking rule. Retired slots28/34
hidden and all cells locked; B52 names all four unused criteria and Manual μ reserve.

Structural allowlist: eleven entries, exactly explained in STRUCTURAL_DIFF.
Only calcChain removed. Other ZIP entries remain byte-identical; expected style
changes are limited to fixed-policy cells and explicit settings protection. Automated
checks include valid XML/ranges, no orphan relationships, max formula2973<8192,
no broken #REF text, deterministic rebuild, emitted-formula golden scenarios.

Runtime three-field and rollback evidence: CALCULATOR_RUNTIME_EVIDENCE.md.
Outputs and production sources are excluded from the review bundle. Expected
runtime changes for each field: xl/worksheets/sheet3.xml + xl/tables/table2.xml.

Native Excel per-field repair/full-recalc/formula-errors/λ/rank/charts/CF gates:
Береговое PENDING; Пырейное PENDING; Хадырьяхинское PENDING.
Seven golden cases and fixed-policy UI inspection: PENDING.
See CALCULATOR_NATIVE_EXCEL_SMOKE.md; a controlled synthetic workbook is included
in the review bundle. Cached blanks before native recalc are not evidence of PASS.

Review bundle produced by scripts/bundle_calculator_review.py includes exact
final/rollback XLSX, hashes, metadata, formula map, audit, migration, tests and
native procedure. No production source workbook or generated production output.

Post-review cleanup preserves the accepted candidate's sheet4/sheet5/sheet6 and
table3/table4 bytes exactly (compared with original a0c8fc… candidate). Formula
and ranking model therefore did not change during this finalization pass.

Canonical status: **candidate**, `canonical=false`.
Corrective diff from previous v0.20 final candidate: only styles.xml and sheet2.xml;
unexpected=0. Formula model unchanged. See CALCULATOR_CORRECTIVE_DIFF.md.
Automated positive/negative OOXML tests verify actual protection and visual parity.
