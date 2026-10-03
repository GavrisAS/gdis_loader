# Production cross-check reconciliation v0.16

Baseline: v0.15 / `ba27e4cb80b4ba5c039371ba4fde3217bec39f70`.
Calculation date: **2026-10-03**. Selected field: **Береговое**. Python: **3.14.7**.
Inputs unchanged from v0.15. Defaults applied; no user config is bundled.

## Source reproducibility

| Role | Actual basename | Bytes | SHA-256 |
|---|---|---:|---|
| calculator | GDIS_Rating_Calculator_FIXED.xlsx | 1886651 | `bb046cc365749a546d1bbe141165b08a664ba427ab9493b678ddce008fc85c6a` |
| fund | Фонд 2026 на 01.08.2026.xlsx | 2332175 | `0ee001ef1cc888492bccd29b11d565a7f0b9d5a64f9c2cfc805d47484f85eeb3` |
| gdi | Сводная таблица ГДИ.xlsx | 3528428 | `2a25663622976f86237be2e1ab8507ae1de189cc83763b70774cc3f245c32d5c` |
| lha | База ЛХА_Итог!.xlsm | 68924956 | `df4062ca25bb6c30e37150f85d56e084f4cbfe28064e4dfa497c32cc46a09bc8` |
| well_history | База по скважинам.xlsx | 542744 | `7e2214316b87067ef2a1da412ac540fe76ac21ad6bf0be620b74311872518dfb` |
| research_status | Статус исследований_2026.xlsx | 5810120 | `af83ddcfe3510f20d4414f5f00d33ba777baab885b3387ad51088d7b5ec1107a` |
| daily_report | 07.2026 Cуточный рапорт БГП_полный.xlsm | 11237181 | `b41493b5b067b127d16fc68c9344e12eeff6d64be222aa67ce4af2fa9227ea4d` |
| generated_calculator | gdis_after.xlsx | 1342490 | `8b7188ad594da512eaf228f5474dcc83cc1671de82e1e25a6e02e2d33f9cd654` |

Criteria snapshot (`criteria_source=defaults`):

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

Manifest derives from runtime SourcePaths, including custom selected basenames. It contains hashes and metadata only: no absolute paths, production bytes, user config or secrets. The final audit stamps exact commit/release metadata. Frozen builds embed the build commit/version; manifest creation does not require a git installation on the target PC.

## Fund object parsing

Exact-source `ПК19-20` remains `ПК19+20`. Fund `Береговой (ПК19-20)` is range 19..20; `ПК9-17` is range 9..17. A composite is compatible only when every primary constituent is inside the range. No fuzzy matching.

| Fund object | Eligible rows | Scope |
|---|---:|---|
| Береговой (ПК 1) | 50 | exact ПК1 |
| Береговой (ПК9-17) | 8 | range |
| Береговой (ПК19-20) | 18 | range |
| Береговой (АТ8-9) | 2 | no exact ПК constraint |

## Lifecycle and reason delta

| GDI status | v0.15 | v0.16 |
|---|---:|---:|
| MATCHED | 58 | 68 |
| NO_GDI | 3 | 7 |
| AMBIGUOUS | 17 | 3 |

All 17 old ambiguous rows had `WELL_HISTORY_STAGE_AMBIGUOUS`; 14 were caused by the artificial exact fund-plast restriction. Ten become MATCHED; four become NO_GDI; three remain ambiguous. Resolved zero-GDI stages retain count=0, insufficient=Да, durations from effective launch, and never use earlier lifecycle GDI.

| Former ambiguous well | New status | Current event / plast | Reason delta |
|---|---|---|---|
| 10302 | MATCHED | ПВЛГ / ПК16 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 10304 | AMBIGUOUS | unresolved / unresolved | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` retained; current plast outside scope |
| 10306 | NO_GDI | INITIAL / ПК17 | `WELL_HISTORY_STAGE_AMBIGUOUS` removed; `GDI_NOT_FOUND` for current stage |
| 10606 | MATCHED | INITIAL / ПК17 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 54 | MATCHED | ПВЛГ / ПК14 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 10404 | AMBIGUOUS | unresolved / unresolved | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` retained; current plast outside scope |
| 10803 | MATCHED | ПВЛГ / ПК14+15 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 11302 | MATCHED | INITIAL / ПК15 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 10201 | NO_GDI | ЗБС / ПК19 | `WELL_HISTORY_STAGE_AMBIGUOUS` removed; `GDI_NOT_FOUND` for current stage |
| 10202 | MATCHED | ЗБС / ПК19 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 10301 | NO_GDI | ЗБС / ПК19 | `WELL_HISTORY_STAGE_AMBIGUOUS` removed; `GDI_NOT_FOUND` for current stage |
| 10305 | MATCHED | ЗБС / ПК19 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 10401 | NO_GDI | ЗБС / ПК19 | `WELL_HISTORY_STAGE_AMBIGUOUS` removed; `GDI_NOT_FOUND` for current stage |
| 10601 | MATCHED | ПВЛГ / ПК19 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 10701 | MATCHED | INITIAL / ПК19 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 10702 | MATCHED | INITIAL / ПК19 | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` removed; range compatible, MATCHED |
| 10503 | AMBIGUOUS | unresolved / unresolved | `WELL_HISTORY_STAGE_AMBIGUOUS` and `GDI_AMBIGUOUS_MATCH` retained; current plast outside scope |

Remaining true conflicts: 10304 has current ПК19+20 outside fund ПК9-17; 10404 has current АТ8-1-1 outside fund ПК9-17; 10503 has current А8-1-1 outside fund ПК19-20. No equivalence is inferred.

Current-fund reason delta: `WELL_HISTORY_STAGE_AMBIGUOUS` 17 → 3 affected rows; `GDI_AMBIGUOUS_MATCH` 17 → 3; `GDI_NOT_FOUND` 3 → 7. Successful MATCHED rows have no replacement warning.

Current resolved fund stage counts: INITIAL=45, ЗБС=26, ПВЛГ=4, ПНЛГ=0; unresolved=3. These are fund rows, not distinct historical identities.

Cross-check comparison: 0 output count mismatches; 1,599 deduplicated valid GDI source rows; 750 current post-launch rows; 16 pre-launch exclusions. Audit-only timeline cross-check adds one unresolved-fund ZBS identity (27 vs 26 strict resolved rows); it never changes output eligibility.

## Identity inheritance and controlled cases

PVLG/PNLG inherit their confirmed parent canonical identity; source suffix is not display identity. Explicit ZBS ordinals select a branch before latest-stage logic and retain its latest PVLG/PNLG stage. Synthetic tests cover simultaneously working ЗБС/ЗБС2 and root-only active sibling ambiguity. GS/MZS normalization and separate histories are unchanged.

| Controlled well | Fund object | Current stage | Canonical plast | Parent identity | Target identity | GDI |
|---|---|---|---|---|---|
| 10606 | Береговой (ПК9-17) | INITIAL (2021) | ПК17 | — | 10606 | MATCHED |
| 54 | Береговой (ПК9-17) | ПВЛГ (2025) | ПК14 | 54 | 54 | MATCHED |
| 10803 | Береговой (ПК9-17) | ПВЛГ (2025) | ПК14+15 | 10803 | 10803 | MATCHED |
| 11302 | Береговой (ПК9-17) | INITIAL (2022) | ПК15 | — | 11302 | MATCHED |
| 10302 | Береговой (ПК9-17) | ПВЛГ (2024) | ПК16 | 10302_ЗБС | 10302_ЗБС | MATCHED |
| 10601 | Береговой (ПК19-20) | ПВЛГ (2024) | ПК19 | 10601_ЗБС | 10601_ЗБС | MATCHED |

10302: confirmed ЗБС → ПВЛГ, inherited `10302_ЗБС`; 10601: confirmed ЗБС → ПВЛГ, inherited `10601_ЗБС`. Both have direct production regression assertions. Current INITIAL histories retain their root identities.

## Independent sources

| Filled cells | v0.15 | v0.16 | Recovered |
|---|---:|---:|---:|
| Дебит | 49 | 63 | 14 |
| Проблемы ГДМ | 46 | 49 | 3 |
| Cl текущий | 57 | 71 | 14 |
| ВГФ текущий | 57 | 71 | 14 |

All 14 recovered Debit rows previously failed lifecycle resolution through the incorrect fund exact-plast constraint. Daily mapping now succeeds after lifecycle correction. GDI-status gating is separately proven by parameterized MATCHED/NO_GDI/AMBIGUOUS tests: identical known lifecycle and sources produce the same Debit/GDM/Cl/VGF. Production has no additional GDI-only ambiguity with a resolved stage; the remaining 3 ambiguities concern lifecycle itself. LHA maximum duplicate behavior is unchanged. Explicit suffix rows also undergo temporal assignment: pre-PVLG LHA is excluded despite an inherited identical display identity; GDM with an explicit ordinal follows its own active branch despite a newer sibling. These safeguards preserve the production output SHA-256.

| Recovered Debit target | Previous status | Reason |
|---|---|---|
| 10302_ЗБС | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10306 | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10606 | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 54 | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10803 | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 11302 | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10201_ЗБС3 | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10202_ЗБС | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10301_ЗБС | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10305_ЗБС | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10401_ЗБС | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10601_ЗБС | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10701 | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |
| 10702 | AMBIGUOUS | fund range resolves current identity; daily field/well assignment unique |

Debit blanks: 15 = 12 `DEBIT_SOURCE_FIELD_AMBIGUOUS` + 3 `DEBIT_LIFECYCLE_UNRESOLVED`. This exceeds the historical v0.14 fill count 57 through confirmed assignments, not by targeting a count.

GDM blanks: 29 = 19 `GDM_FALLBACK_OUTSIDE_WINDOW` + 5 `GDM_CURRENT_HISTORY_NOT_FOUND` + 2 `GDM_DELTA_MISSING_OR_INVALID` + 3 `GDM_LIFECYCLE_UNRESOLVED`. Recovered GDM targets: `10305_ЗБС`, `10701`, `10702`. Three recovered filled cells reflect corrected current history/plast; Delta semantics and fallback window remain unchanged.

LHA current Cl/VGF blanks: 7; no gate on GDI MatchStatus.

## Customer examples

| Well | GDI count |
|---|---:|
| 12 | 20 |
| 13 | 21 |
| 21 | 19 |
| 22 | 19 |

## OOXML and comparison layer

Changed ZIP entries: only `xl/worksheets/sheet3.xml` and `xl/tables/table2.xml`. All other entries are byte-identical. `tblData=A6:Z84`, CF=`A7:A84`; x14ac namespace and Ignorable preserved. Exactly 78 written rows; no stale data rows. Formula layer/calculation settings/relationships remain byte-identical.

This is **cross-check reconciliation**. Canonical normalization, classification, lifecycle resolution and dedupe are shared business primitives. Output cells are independently re-read with openpyxl; the comparison layer checks counts and OOXML bytes. It is not a fully independent reimplementation.

## Deferred

Formula-layer μ/λ migration, weights and structural cleanup remain deferred; see [STRUCTURAL_CALCULATOR_MIGRATION.md](STRUCTURAL_CALCULATOR_MIGRATION.md). No other calculator parts or production inputs were modified.
