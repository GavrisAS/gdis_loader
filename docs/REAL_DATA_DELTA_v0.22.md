# Production delta — v0.22

Same updated source bundle for baseline v0.21 code and v0.22 code; calculation date
2026-08-01 (Fund snapshot). This isolates business-rule changes from source changes.
A separate integration golden uses 2026-10-02; age-sensitive Delta counts differ.

| Field | Eligible / written | MATCHED before → after | AMBIGUOUS before → after | NO_GDI before → after | Summary selections | Overrides Fund / Base |
|---|---:|---:|---:|---:|---:|---:|
| Береговое | 78 | 71 → 77 | 3 → 0 | 4 → 1 | 77 | 27 / 6 |
| Пырейное | 5 | 5 → 5 | 0 → 0 | 0 → 0 | 3 | 0 / 0 |
| Хадырьяхинское | 10 | 9 → 9 | 0 → 0 | 1 → 1 | 6 | 0 / 0 |

INVALID_SOURCE=0 in all fields. Authoritative Summary takes precedence even for
a confirmed current ПК19 history: count8 replaces stale ПК19+20/count0. Historical GDI is
still excluded when its plast or confirmed lifecycle differs. Fund/Base overrides
can overlap; they are not added together.

| Field | Selected Δ 2026 / 2025 / 2024 | Fallback past invalid latest | Rejected different plast targets / history targets | Too old | No valid Δ (including too old) |
|---|---:|---:|---:|---:|---:|
| Береговое | 18 / 23 / 7 | 16 | 19 / 9 | 23 | 30 |
| Пырейное | 0 / 0 / 0 | 0 | 0 / 0 | 2 | 5 |
| Хадырьяхинское | 0 / 6 / 0 | 0 | 1 / 2 | 0 | 4 |

Year categories refer to selected value year relative to calculation year, whether
or not the latest source row was invalid. The existing fallback counter specifically
counts searches past an invalid latest relevant row. Rejection categories count
targets with grouped diagnostics and can overlap; they are not a partition of wells.
No valid Δ excluding age-only rejection: 7 / 3 / 4. A numeric value without a
confirmed current history is now blank, including previously allowed exact-identity
GDM matches on unresolved histories. On Хадырьяхинское this changes selected9→6.

Baseline selected values: Береговое2026:18, 2025:20, 2024:11, 2023:1;
Пырейное0; Хадырьяхинское2025:9. Removing unbounded latest-value acceptance and
anchoring age to calculation date can reduce coverage even with a larger default.

All six before/after outputs have exactly the expected changed ZIP parts:
`xl/worksheets/sheet3.xml`, `xl/tables/table2.xml`. No other payload or ZIP name
changes. Templates are unchanged; outputs and raw production reports remain local
and are excluded from the review bundle. Machine-readable aggregates and grouped
diagnostic-code counts are included in `production_summary.json` in that bundle.
