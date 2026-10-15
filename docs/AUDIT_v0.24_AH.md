# v0.24 AH corrective qualification

Baseline: 222d4b4509b3686946160317aa32e1bd798d7495. This pass preserves the
September matching semantics and adds an explicit `column == "AH"` requirement
to direct dated telemetry reference evidence. Other columns cannot prove scope,
even when the telemetry cache is positive. No thresholds or templates changed.

## Fresh production qualification

The complete Beregovoe update was rerun with calculation_date=2026-10-12 and
default criteria, on exactly the input hashes and criteria snapshot of the
retained v0.23 September baseline. The reconciler asserts all input hashes and
criteria agree, checks every output row, and rejects changes to non-debit fields.

| Check | Result |
|---|---:|
| Eligible | 78 |
| Filled | 75 |
| Blank | 3 |
| Previously filled and unchanged (rel_tol=1e-12, abs_tol=1e-10) | 63 |
| Recovered with complete daily evidence | 12 |
| Independent raw XML daily reference/cache checks | 2340 |
| Accepted non-AH destinations | 0 |
| Non-AH direct references in source telemetry (including unselected rows) | 0 |
| Selected rows affected by non-AH rejection | 0 |
| Positive numeric days in each remaining blank | 0 of 30 |
| Unexpected non-debit changes | 0 |

Source: `09.2026 Cуточный рапорт БГП.xlsm`, authoritative sheet
`Добыча телеметрия`, SHA-256
`56fb8f826fe70671ebc0a69bb5fc80c62ef63a64f1cbab30e7d3530e996151b3`.
Period: September 1–30, 2026; undated day 31 is excluded. The independent
ZIP/XML checker uses neither application readers nor reference evidence helpers.
It verifies direct AH destination, daily date, both well identities, telemetry
cache against destination cache, and arithmetic mean of finite rates > 0.
Full coordinates, lifecycle evidence, input/config/output hashes and all 78
row comparisons remain in ignored local `artifacts/v0.24/`.

## Regression evidence

Synthetic tests accept AH8/$AH8/AH$8/$AH$8 and reject D/AB/AG/other destinations,
wrong well/day/sheet, conflicting secondary identity, unknown section,
INDIRECT, external books, and compound expressions. Reader/selector tests inject
positive caches into AH/D/AB/AG references: only AH supplies field evidence and
a selectable debit source. Cross-field and branch controls vary well numbers,
row coordinates and ordering. No Pyreinoe or Khadyr'yakhinskoye production PASS
is claimed; these fields have synthetic controls only.

## Preservation and public safety

Structural v3 remains SHA-256
`6a7523fdbf524fd9b7f6709d0b3b95279641c706f958c36d388a41c23d610248`.
The runtime output changes only `xl/worksheets/sheet3.xml` and
`xl/tables/table2.xml`; all other ZIP parts are byte-identical. Capacity remains
1000; v2/rollback are untouched. Native Excel v3 acceptance remains PENDING,
canonical=false; automated qualification supports a candidate only.

All 556 reachable historical content blobs were scanned for common private-key,
GitHub-token and AWS-access-key patterns: no matches. Historical path inventory
contains no data workbook, runtime config, or archive; `data/README.md` is the
only tracked data path. This pattern scan cannot prove absence of every secret.
The user explicitly authorized retaining already public audit identities in
history and publishing the existing populated template examples. Current audit
prose removes unnecessary production source-row coordinates. Production books,
full reconciliation and private logs are excluded from the review ZIP.

## Gates

Fresh local `uv sync --locked` and `make check` passed: Ruff lint/format, ty,
and **604 tests passed** (one openpyxl extension warning), Python 3.14.7.
The template acceptance audit and strict runtime source/output revalidation passed.

Fresh local gate results and exact final-commit Actions run URLs are supplied in
the final review bundle's gate evidence. The earlier refused runs on 222d4b4 are
not execution evidence. Push to main invokes the existing CI and Build Windows
workflows using standard ubuntu-latest/windows-latest runners. Release job needs
both its Linux checks and the Windows build/frozen smoke to succeed; tags are
created once at github.sha. A final handoff records independent CI conclusions,
release asset checksums and metadata after those jobs finish.
