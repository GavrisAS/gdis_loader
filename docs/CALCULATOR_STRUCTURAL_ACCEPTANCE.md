# Structural template v2 acceptance

Automated structural acceptance: **PASS**.
Overall: **AUTOMATED PASS / NATIVE EXCEL PENDING**.
`uv sync --locked` and `make check`: PASS, Python3.14.7; 480 tests passed.
Native Excel acceptance: **PENDING — NOT EXECUTED**.
Canonical status: **candidate**. Native Excel is a mandatory independent gate.

Durable storage: option A, tracked repository assets under templates/calculator.
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
protection. Existing yellow input styles explicitly unlocked. Retired slots28/34
hidden; B52 names all four unused criteria and Manual μ reserve.

Structural allowlist: eleven entries, exactly explained in STRUCTURAL_DIFF.
Only calcChain removed. Other ZIP entries remain byte-identical; expected style
changes are limited to fixed-policy cells and yellow input protection. Automated
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
