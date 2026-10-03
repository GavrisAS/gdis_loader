# Final verification summary

Python 3.14.7 / uv locked environment. Required quality run: uv sync --locked
and make check (ruff check, ruff format --check, ty check, pytest).
Final full run status: PASS; 500 passed in 464.34s, no failures.
One openpyxl warning came from read-only-in-purpose inspection of x14 conditional
formatting; no workbook round-trip/save was performed. OOXML retains extensions.

Structural suite: 40 passed, including deterministic repeated migration,
exact eleven-entry allowlist, unchanged non-target parts, input schema26,
1000-row capacity, emitted-formula golden cases and all-unknown rank guard.
Read-only capabilities suite: 15 passed; old100 and v2 1000; boundary writer
warnings; fixed settings locked with no dropdown; explicit general inputs unlocked;
unknown capacity and template-aware diagnostic.
Three-field v2 and rollback production updates: PASS; only sheet3.xml/table2.xml
changed, source templates unchanged. No production workbook included in review.

Native Excel and real Excel golden evaluation: PENDING, not substituted by tests.

Corrective positive/negative editability tests: 20 passed. Actual cellXfs
protection and sheetProtection verified; retired cells locked and rows hidden;
clones preserve visual attributes. Repeated local builds are byte-deterministic. Cross-platform rebuild equals
tracked OOXML payloads; ZIP compression bytes may differ between zlib builds.
Protection fix adds no formula changes.
