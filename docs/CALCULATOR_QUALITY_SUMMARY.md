# Final verification summary

Python 3.14.7 / uv locked environment. Required quality run: uv sync --locked
and make check (ruff check, ruff format --check, ty check, pytest).
Final full run status: PASS; 480 passed in 453.25s, no failures.
One openpyxl warning came from read-only-in-purpose inspection of x14 conditional
formatting; no workbook round-trip/save was performed. OOXML retains extensions.

Separate structural suite: 20 passed, including deterministic repeated migration,
exact eleven-entry allowlist, unchanged non-target parts, input schema26,
1000-row capacity, emitted-formula golden cases and all-unknown rank guard.
Read-only capabilities suite: 15 passed; old100 and v2 1000; boundary writer
warnings; fixed settings locked with no dropdown; ordinary inputs unlocked;
unknown capacity and template-aware diagnostic.
Three-field v2 and rollback production updates: PASS; only sheet3.xml/table2.xml
changed, source templates unchanged. No production workbook included in review.

Native Excel and real Excel golden evaluation: PENDING, not substituted by tests.
