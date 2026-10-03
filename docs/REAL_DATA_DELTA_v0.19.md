# Production correction v0.18 → v0.19

Baseline: published v0.18, commit `0215efcfa86afe6fda3d1c9e3add7e075a213ae9`.
Calculation date: **2026-10-03**, Python **3.14.7**. Full `run_update(field)`
was executed before and after the correction for all three discoverable fields.
All seven input sizes/SHA-256 are unchanged from the table in
[REAL_DATA_DELTA_v0.18](REAL_DATA_DELTA_v0.18.md). Inputs were read only.
No full production rows, private paths or workbook bytes are included here.

## Per-field comparison

Status order below is MATCHED / NO_GDI / AMBIGUOUS.

| Field | Eligible rows | v0.18 statuses | v0.19 statuses | Changed rows | Changed cells | Valid post-launch GDI sum |
|---|---:|---|---|---:|---:|---:|
| Береговое | 78 | 71 / 4 / 3 | 71 / 4 / 3 | 0 | 0 | 762 |
| Пырейное | 5 | 3 / 0 / 2 | 5 / 0 / 0 | 2 | 31 | 23 |
| Хадырьяхинское | 10 | 9 / 1 / 0 | 9 / 1 / 0 | 0 | 0 | 55 |

All fields were discovered by validate and updated successfully.
Cross-check reconciliation using shared canonical business primitives found
**0 application count mismatches** in every field. Independently read output
count sums equal deduplicated valid current post-launch source counts above.
This is cross-check reconciliation, not an independent business implementation.

| Field | Debit filled before → after | LHA Cl/VGF filled before → after | GDM Да/Нет/blank before → after | Each duration filled before → after |
|---|---|---|---|---|
| Береговое | 63 → 63 | 71/71 → 71/71 | 5/45/28 → 5/45/28 | 75 → 75 |
| Пырейное | 0 → 0 | 3/3 → 5/5 | 0/0/5 → 0/0/5 | 3 → 5 |
| Хадырьяхинское | 0 → 0 | 8/8 → 8/8 | 2/7/1 → 2/7/1 | 9 → 9 |

## Пырейное: controlled wells

Both fund objects are `Пырейный (ПК 1)` with exact scope **ПК1**. Initial
history raw plast **ПК_1** formerly stayed ПК_1; now canonical **ПК1** agrees
with GDI raw ПК-1. Both retain confirmed **INITIAL** lifecycle and target
identity **22** / **62**, with no inferred boundary or suffix change.

| Field / well | Status before → after | Valid GDI count | Effective launch | Without GDI / ID / KVD (years) | Changed cells |
|---|---|---:|---|---|---:|
| Пырейное / 22 | AMBIGUOUS → MATCHED | 11 | 2008-05-01 | 454/365 / 986/365 / 454/365 | 16 |
| Пырейное / 62 | AMBIGUOUS → MATCHED | 4 | 2008-11-01 | 454/365 / 3710/365 / 454/365 | 15 |

The resolved history fills plast, launch, GDI count, three durations, specific
GDI, insufficient flag, LND, downhole flag, current/previous Cl and VGF,
chlorine growth for both; productivity additionally fills for well 22.
Debit and GDM remain blank for both, as supported by independent sources.
The other three eligible Пырейное rows retain every output value.
This is removal of a parser-induced false ambiguity, not relaxed matching.

## Береговое: no regression

All 78 rows retain every output value. Customer counts are explicitly field
scoped: **Береговое 12=20, 13=21, 21=19, 22=19**.
10301_ЗБС remains MATCHED/count **10**; 10401_ЗБС remains MATCHED/count **1**.
10405 remains current **ПК19+20**, NO_GDI/count **0**; single ПК19 research
cannot satisfy joint plast. 10201_ЗБС3 remains count **1**, launch 2026-01-22;
annotated family assignment and ordinal sibling constraints are preserved.
112_ЗБС remains count **4**, GDM **Нет**. 10306 remains INITIAL/count **0**,
NO_GDI with `GDI_UNCONFIRMED_LIFECYCLE_RECORDS`; no missing ZBS is inferred.
10304, 10404 and 10503 remain AMBIGUOUS under unchanged source conflicts.
Source duplicate/prefix rules and pre-launch exclusion are unchanged.

## Хадырьяхинское and underscore inventory

Current eligible output: **10** rows, **9 MATCHED / 1 NO_GDI / 0 AMBIGUOUS**.
The NO_GDI row has no confirmed history/valid assignable GDI; it is not an
underscore-induced ambiguity. There are **0 changed output cells**.
Inventory scans every worksheet of all seven source roles, including historical
and non-eligible rows. Candidate coverage is lineage coverage, not automatic
assignment or proof that a source row passes current lifecycle/plast/date filters.

| Raw plast | Cells | Canonical v0.18 | Canonical v0.19 | Source roles | Eligible candidate coverage |
|---|---:|---|---|---|---|
| ПК_1 | 13 | ПК_1 | ПК1 | well_history | Пырейное: 3 |
| ПК20_2 | 60 | ПК20_2 | ПК20 | lha | Хадырьяхинское: 1 |
| ПК20_0_1 | 2 | ПК20_0_1 | ПК20 | research_status | 0 |

No other underscore ПК forms were found. Calculator, fund, GDI and daily report
contain zero such cells. The two ПК20_0_1 rows are outside current eligible fund
coverage. ПК20_2 has one eligible lineage candidate, but no changed output:
the candidate lacks an unambiguous current history assignment; current filters
remain mandatory. The third Пырейное history candidate already has current
ЗБС/ПК1 from a non-underscore event; its output remains unchanged. Historical presence
of the defect remains covered by grammar tests even without a current cell delta.
Inventory is reproducible using `scripts/inventory_plasts.py --underscore` with
a runtime report and local source directory; only aggregates are exported.

## Grammar and scope

Parameterized tests cover `ПК_1 → ПК1`, `ПК20_2 → ПК20`,
`ПК20_0_1 → ПК20`, `ПК19_1+2 → ПК19`, `ПК19_2+1? → ПК19`.
`ПК19-1+2`, `ПК-19-1+2`, `ПК17-2-1`, `ПК14-1` retain single-primary semantics.
`ПК19-20`, `ПК19-2+20`, `ПК19/2+ПК20`, `ПК19-ПК20 → ПК19+20`;
`ПК14+15` remains joint. Single and joint plasts are unequal.
Underscore is a parser token only inside ПК grammar; well-id suffixes and
arbitrary strings are preserved. Fund ПК9-17 remains range/group semantics.
History, GDI, LHA, research-status/GDM share the same exact-plast canonicalizer.
No fuzzy matching, lifecycle inference or criteria changes were added.

## OOXML evidence for all fields

| Field | tblData | Managed CF | Last data row |
|---|---|---|---:|
| Береговое | A6:Z84 | A7:A84 | 84 |
| Пырейное | A6:Z11 | A7:A11 | 11 |
| Хадырьяхинское | A6:Z16 | A7:A16 | 16 |

Each output differs from the template in exactly `xl/worksheets/sheet3.xml`
and `xl/tables/table2.xml`. All other ZIP entries are byte-identical; x14ac,
its namespace and mc:Ignorable are preserved. No stale target rows remain;
table/CF refs follow actual row counts. Existing single-cell CF G15 is retained.
Formula sheets, calculation settings and non-target parts remain unchanged.

## Audit and reproducible validation

`uv sync --locked`, `make check` and production integration are required locally.
The added suite updates all three fields, verifies OOXML, reconciles counts and
checks controlled Пырейное counts only when baseline source hashes match.
CI skips production tests when local source bytes are absent.

Strict runtime audit now reopens **7/7 inputs plus generated calculator**.
Output basename/size/SHA-256 must match runtime evidence. Tests cover unchanged
output, modified bytes, same-basename different file, missing path/file/entry,
and no private-path leakage. Audit schema is explicitly **manifest_version=4**;
legacy provenance compatibility, source revalidation and commit/tag guards remain.
Criteria snapshot stays at the unchanged default numeric values in v0.18.
Runtime and audit timestamps remain separate. One final strict archive is made
per field from clean tagged release runtime reports; source workbooks, generated
workbook bytes, user config and full runtime JSON/log are excluded.

Structural μ/λ migration remains **deferred**, to begin as a separate stage
after acceptance of v0.19. No weights or Расчет/Рейтинг/Настройки changes occurred.
