# Production reconciliation v0.17

Baseline: published v0.16 / `9791a33df0570a5900f3488a86fcd0f84babd3e4`.
Selected field: **Береговое**. Calculation date: **2026-10-03**. Python **3.14.7**.
Default criteria; same 7 production inputs as v0.16, byte sizes and SHA-256 equal.
This is a code-only delta. Production inputs were only read.

## Aggregate v0.16 → v0.17

| Metric | v0.16 | v0.17 |
|---|---:|---:|
| MATCHED | 68 | 69 |
| NO_GDI | 7 | 6 |
| AMBIGUOUS | 3 | 3 |
| Written rows | 78 | 78 |
| Insufficient GDI = Да | 8 | 8 |
| Productivity filled | 61 | 61 |
| LND = Да | 29 | 30 |
| Downhole = Да | 17 | 18 |
| Specific GDI filled | 68 | 69 |
| Debit filled | 63 | 63 |
| Current Cl filled | 71 | 71 |
| Current VGF filled | 71 | 71 |
| GDM = Да | 5 | 5 |
| GDM = Нет | 44 | 45 |
| GDM blank | 29 | 28 |
| GDM fallback selected | 11 | 12 |
| GDM stale fallback rejected | 17 | 16 |

Valid deduplicated current post-launch GDI: **750 → 751**. Source classification
and dedupe unchanged: 1,599 valid deduplicated rows, 1,830 retained total,
2 exact duplicates collapsed, 16 pre-launch exclusions. Reconciliation reuses
canonical business primitives but independently reads calculator cells:
**0 count mismatches**. It is a cross-check, not an independent business implementation.

Exactly **2 of 78 output rows changed**, **7 cells** in total:

| Target | Changed fields | Reason |
|---|---|---|
| 10201_ЗБС3 | count, LND, downhole, duration without GDI/KVD, specific GDI (6 cells) | annotated ZBS family no longer forces ordinal 1 |
| 112_ЗБС | GDM criterion (1 cell) | no-separator spelling now equals explicit current branch |

Reason distribution: annotated-family resolution **1 target**; no-separator
canonicalization **1 target**. Other **76 output rows byte-value equivalent**,
including target identities, Debit, Cl/VGF and productivity. Two duration values
changed for 10201; other durations unchanged. No target display identity changed.

## Controlled cases

| Root | Current lifecycle / target | Current plast | GDI status / count | GDM result | Reason |
|---|---|---|---|---|---|
| 10201 | ЗБС3 / 10201_ЗБС3; launch 2026-01-22 | ПК19 | MATCHED / 1 (was NO_GDI / 0) | blank | annotated family resolves against current timeline; no valid current Delta |
| 112 | ЗБС / 112_ЗБС; launch 2022-12-01 | ПК1 | MATCHED / 4 | Нет (was blank) | 112збс canonicalized; nearest valid in-window fallback restored |
| 10304 | unresolved / 10304 retained | blank; conflicting history ПК19+20 | AMBIGUOUS / blank | blank | current history plast outside fund scope ПК9-17 |
| 10404 | unresolved / 10404 retained | blank; conflicting history АТ8-1-1 | AMBIGUOUS / blank | blank | current history plast outside fund scope ПК9-17 |
| 10503 | unresolved / 10503 retained | blank; conflicting history А8-1-1 | AMBIGUOUS / blank | blank | current history plast outside fund scope ПК19-20 |

No remaining source conflict was guessed away. GS/MZS remain separate identities;
PVLG/PNLG inherit confirmed parent identity including ordinal ZBS. Six current
zero-GDI rows retain count=0, insufficient=Да, durations from launch, specific
GDI blank; old-lifecycle fallback remains prohibited. Independent sources have
no MATCHED gate.

### 10201

History: INITIAL ПК20 (~2015), ЗБС АТ8-1-1 (~2023), ЗБС2 ПК19 (~2024),
ЗБС3 ПК19 (2026-01-22). `_ЗБС_МГРП` has family ЗБС, ordinal **None**,
not ordinal 1. Confirmed timeline + current plast + date assign the valid KVD
on **2026-04-05** (`КВД при ПГИ`) to **ЗБС3**, never ЗБС1.
The 2026-03-20 освоение and 2026-07-12 Pст rows remain EXCLUDED under the
confirmed prefix classifier. The selected KVD has RFP=нет and LND reliability=низкая.

Last KVD / last valid GDI: **2026-04-05**. Count **1**, insufficient **Да**.
Duration without GDI and KVD: **181/365 = 0.4958904109589041 years**;
without ID remains lifecycle age **254/365**. Specific GDI:
**(254/365)/1 = 0.6958904109589041**.
Actual source evidence gives **ЛНД=Да**, **Глубинные датчики=Да**.
Productivity decline remains **blank**, insufficient valid numeric-a comparisons.
Values are derived from current source, not hardcoded.

### 112

`112збс -> 112_ЗБС`, same physical root but a separate branch from initial 112.
Latest relevant record **2025-08-30** has missing Delta. Nearest previous valid
record is **2025-02-28**, Delta **−1.3499999999999979** (≈−1.35),
age **183 days** relative to the latest relevant research, inside **365 days**.
With strict `abs(Delta) > 5`, **Проблемы ГДМ=Нет**. Old 2024-03-15 Delta
≈−0.44 is no longer selected/rejected as the nearest fallback. Synthetic tests
also verify this missing-latest / nearest-valid sequence without production rows.

## No-separator inventory: every sheet of all runtime inputs

Counts are source rows, deduplicated by sheet/row; distinct forms expose only
canonical identities. Affected target counts mean eligible Beregovoe physical-root
candidates, not automatic assignments or changed output rows. Other fields' source
records never cross field constraints. Read-only data-only scan excludes formula
strings and does not execute macros.

| Source role | Rows | Distinct canonical forms | Candidate target count |
|---|---:|---|---:|
| calculator | 0 | — | 0 |
| fund | 0 | — | 0 |
| gdi | 5 | 51_ЗБС, 52_ЗБС | 2 |
| lha | 0 | — | 0 |
| well_history | 0 | — | 0 |
| research_status | 23 | 10201_ЗБС_МГРП, 10304_ЗБС, 10403_ЗБС, 10404_ЗБС2, 111_ЗБС, 112_ЗБС, 112_ЗБС_ГС, 113_ЗБС, 11_ЗБС, 201_ЗБС, 203_ЗБС, 212_ЗБС, 54_ГС | 8 |
| daily_report | 0 | — | 0 |

The shared parser reaches fund/GDI/GDM/LHA/daily/history readers. GS/MZS forms
retain separate identities; canonicalization alone never authorizes a branch merge.
Inventory is reproducible with `scripts/inventory_well_ids.py` against the runtime
manifest and local input directory, without printing full source rows.

## Customer reconciliation

| Well | v0.16 | v0.17 |
|---|---:|---:|
| 12 | 20 | 20 |
| 13 | 21 | 21 |
| 21 | 19 | 19 |
| 22 | 19 | 19 |

## Runtime input hashes

| Role | Basename | Bytes | SHA-256 |
|---|---|---:|---|
| calculator | GDIS_Rating_Calculator_FIXED.xlsx | 1886651 | `bb046cc365749a546d1bbe141165b08a664ba427ab9493b678ddce008fc85c6a` |
| fund | Фонд 2026 на 01.08.2026.xlsx | 2332175 | `0ee001ef1cc888492bccd29b11d565a7f0b9d5a64f9c2cfc805d47484f85eeb3` |
| gdi | Сводная таблица ГДИ.xlsx | 3528428 | `2a25663622976f86237be2e1ab8507ae1de189cc83763b70774cc3f245c32d5c` |
| lha | База ЛХА_Итог!.xlsm | 68924956 | `df4062ca25bb6c30e37150f85d56e084f4cbfe28064e4dfa497c32cc46a09bc8` |
| well_history | База по скважинам.xlsx | 542744 | `7e2214316b87067ef2a1da412ac540fe76ac21ad6bf0be620b74311872518dfb` |
| research_status | Статус исследований_2026.xlsx | 5810120 | `af83ddcfe3510f20d4414f5f00d33ba777baab885b3387ad51088d7b5ec1107a` |
| daily_report | 07.2026 Cуточный рапорт БГП_полный.xlsm | 11237181 | `b41493b5b067b127d16fc68c9344e12eeff6d64be222aa67ce4af2fa9227ea4d` |

Criteria snapshot (`criteria_source=defaults`), retained in final source manifest:

```json
{
  "insufficient_gdi": {
    "min_count": 2
  },
  "productivity_decline": {
    "min_increase": 0.0
  },
  "chlorine_growth": {
    "current_min_mg_dm3": 2000.0,
    "delta_min_mg_dm3": 1000.0
  },
  "downhole": {
    "depth_threshold_m": 0.0
  },
  "gdm": {
    "abs_delta_threshold": 5.0,
    "fallback_max_age_days": 365
  },
  "gas_rate": {
    "working_day_min_rate": 0.0
  }
}
```

Runtime input basenames/size/hash come from actual SourcePaths. Generated
calculator hash is stored in the runtime source manifest if available. Final
release audit reruns production on the clean tagged commit and verifies identical
7 input hashes; generated workbook, full runtime report/log and user config are
not bundled. Runtime/audit timestamps and commit/tag are separate; known mismatch
fails instead of mutating runtime evidence. See [AUDIT_PROVENANCE.md](AUDIT_PROVENANCE.md).

## OOXML invariants

Exactly **78** target rows. `tblData=A6:Z84`; CF `A7:A84`; no stale rows beyond 84.
Changed ZIP entries are only `xl/worksheets/sheet3.xml` and `xl/tables/table2.xml`.
Every other entry is **byte-identical** to the input calculator. x14ac namespace
and `mc:Ignorable` preserved. Formula sheets, settings, weights, relationships and
calculation layer remain unchanged. Assertions are exercised by real-data integration tests.

## Deferred

Structural μ/λ migration, Расчет/Рейтинг/Настройки changes, weights and physical
criterion removal remain deferred to a separate iteration.
