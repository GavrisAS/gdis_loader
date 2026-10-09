# Current verification — v0.23 / structural v3

Local gates: `uv sync --locked`, `make check` (Ruff, format, ty, pytest).
Current complete evidence: [AUDIT_v0.23.md](AUDIT_v0.23.md) and the final review bundle.
The regression suite grows from 516 to 569 cases; none is removed.

Structural v3 exact five-part gate preserves all formula sheets, λ/rank, charts,
styles, protection, calculation capacity 1000 and auto-recalculation. Writer
checks v1/v2/v3 by named headers, including Manual μ in legacy workbooks.
Accepted v2 SHA-256 remains unchanged. No calcChain is added.

v2 native Excel PASS was confirmed 2026-10-07. v3 requires new acceptance:
NATIVE EXCEL PENDING / CANDIDATE, canonical=false. Automated OOXML tests do
not replace Microsoft Excel. Production sources and filled output books stay local.
