# Production cross-check reconciliation v0.18

Baseline: v0.17 / `01eb28007926c67331c4839632b81f488cbc787b`.
Selected field **Береговое**, calculation date **2026-10-03**, Python **3.14.7**.
All seven input sizes and hashes equal v0.17. Actual files were reopened and
rehashed: **7/7 matched**. Final release audit repeats strict revalidation after
rerunning production on the tagged clean commit. Shared business primitives are
used; this is cross-check reconciliation, not a fully independent implementation.
Production inputs were read only; no full production rows are included here.

## Parser grammar and inventory

The old split("+") mistook sublayers for primary plasts:
`ПК19-1+2 → ПК2+19`, `ПК19-2+1? → ПК1+19`.
The parser now builds immutable primary components with subordinate numbers.
`ПК19-1+2`, `ПК-19-1+2`, `ПК19-2+1?`, `ПК14-1+2` keep a single primary.
`ПК19-20`, `ПК19-2+20`, `ПК19/2+ПК20`, `ПК19 + ПК20` remain `ПК19+20`.
`ПК14+15` remains joint. Explicit family tokens start primary components,
including `ПК19-ПК20`; one-digit bare plus tokens continue an active sublayer.
No fuzzy matching or primary-only/composite equivalence is introduced.

Read-only scan of every worksheet in all seven source workbooks, reproducible
with `scripts/inventory_plasts.py`:

| Source | Shorthand cells | Distinct raw forms | New canonical |
|---|---:|---:|---|
| GDI | 30 | 1 | ПК19 |
| LHA | 6 | 1 | ПК19 |
| Research status | 7 | 2 | ПК19 |
| Calculator/fund/history/daily | 0 | 0 | — |

Across all sources: **3 distinct raw shorthand forms**, all **3** change
canonical plast, touching **5 eligible selected-field target wells** (candidate
coverage, not automatic assignment). All **43** shorthand cells change canonical interpretation. The GDI business
reader retains **28** of those source rows, spanning **4** physical roots and
**3** eligible selected-field targets: 10301, 10401, 10405. Only the first two
change GDI output; 10405 remains an exact-plast negative control. Raw spelling
counts are per source (overlap is possible). Distinct shorthand forms across
sources are counted by the script; no source row payload is exported.

## Aggregate v0.17 → v0.18

| Metric | v0.17 | v0.18 |
|---|---:|---:|
| MATCHED | 69 | 71 |
| NO_GDI | 6 | 4 |
| AMBIGUOUS | 3 | 3 |
| Written rows | 78 | 78 |
| Insufficient = Да | 8 | 7 |
| Insufficient = Нет | 67 | 68 |
| LND = Да | 30 | 32 |
| LND = Нет | 7 | 7 |
| Downhole = Да | 18 | 19 |
| Downhole = Нет | 48 | 49 |
| Productivity filled | 61 | 62 |
| Specific GDI filled | 69 | 71 |
| GDM = Да | 5 | 5 |
| GDM = Нет | 45 | 45 |
| GDM blank | 28 | 28 |
| GDM candidate rows | 54 | 61 |
| GDM stale fallback rejected | 16 | 17 |
| Debit filled | 63 | 63 |
| Debit valid days | 1505 | 1505 |
| Cl filled | 71 | 71 |
| VGF filled | 71 | 71 |
| Duration without GDI filled | 75 | 75 |
| Duration without ID filled | 75 | 75 |
| Duration without KVD filled | 75 | 75 |

Deduplicated valid current post-launch GDI: **751 → 762**. Source dedupe and
prefix classifier unchanged; 1,830 retained rows, 2 collapsed exact duplicates,
16 pre-launch exclusions. Three output rows changed, **19 cells**: 10301 (9),
10401 (6), 10605 (4). Other 75 target rows retain all values. Only four duration
cells change: without GDI/KVD for 10301 and 10401; ID durations remain equivalent
to lifecycle age for 10401 and latest valid ID for 10301. Filled duration counts
remain 75 each. No display identity, Debit, or GDM output changed. Cross-check reconciliation
reports **0 application count mismatches**.

The additional LHA delta is explained by a distinct grammar defect:
`ПК19-ПК20` formerly lost its explicit second primary token. It now equals
current `ПК19+20` for 10605. Current/previous Cl becomes **9987/6670** instead of
**6670/24396**, current VGF **9.006** instead of **0**, growth **Да** instead of
**Нет**. New point 2025-08-16 replaces the 2024-01-22 point; old previous point
2024-01-21 is no longer the nearest previous. Exact numeric thresholds are
unchanged; this is source eligibility, not a change of criteria semantics.

## Controlled wells

| Root | Confirmed lifecycle / target | Canonical plast | Status/count before → after | GDM | Reason |
|---|---|---|---|---|---|
| 10301 | ЗБС / 10301_ЗБС; launch 2022-04-01 | ПК19 | NO_GDI/0 → MATCHED/10 | blank | current shorthand becomes exact ПК19 |
| 10401 | ЗБС / 10401_ЗБС; launch 2025-12-07 | ПК19 | NO_GDI/0 → MATCHED/1 | blank | valid 2026-07-22 КВД глубинн restored |
| 10405 | INITIAL / 10405; launch 2014-11-01 | ПК19+20 | NO_GDI/0 → NO_GDI/0 | blank | single ПК19 does not cover joint ПК19+20 |
| 10201 | ЗБС3 / 10201_ЗБС3; launch 2026-01-22 | ПК19 | MATCHED/1 → MATCHED/1 | blank | annotated family remains assigned current stage |
| 112 | ЗБС / 112_ЗБС; launch 2022-12-01 | ПК1 | MATCHED/4 → MATCHED/4 | Нет | nearest valid fallback preserved |
| 10306 | INITIAL / 10306; launch 2023-12-01 | ПК17 | NO_GDI/0 → NO_GDI/0 | blank | no confirmed ZBS boundary |
| 10304 | unresolved / 10304 | blank | AMBIGUOUS → AMBIGUOUS | blank | current history ПК19+20 outside fund ПК9-17 |
| 10404 | unresolved / 10404 | blank | AMBIGUOUS → AMBIGUOUS | blank | current history АТ8-1-1 outside fund ПК9-17 |
| 10503 | unresolved / 10503 | blank | AMBIGUOUS → AMBIGUOUS | blank | current history А8-1-1 outside fund ПК19-20 |

### 10301

Valid current exact-plast GDI: **7 KVD + 3 ID_KVD = 10**. One current ПК19
EXCLUDED research is not counted; Pст/non-prefix records remain excluded.
Latest valid GDI/KVD: **2026-07-14**. Insufficient **Да → Нет**, LND **blank → Да**,
downhole **blank → Нет**, productivity **blank → Да** (valid numeric-a rows).
Without GDI/KVD **81/365 = 0.2219178082191781 years**; without ID
**1261/365 = 3.4547945205479453 years**. Specific GDI
**(1646/365)/10 = 0.45095890410958905**. Results are computed from actual sources.

### 10401

Only **2026-07-22 КВД глубинн** is valid after current launch. `МЗС+миниКВД`
remains UNKNOWN/invalid. Count **0 → 1**, insufficient remains **Да**, LND
**blank → Да**, downhole **blank → Да**, productivity remains blank.
Without GDI/KVD **73/365 = 0.2 years**, without ID **300/365 = 0.821917808219178**;
specific GDI **(300/365)/1 = 0.821917808219178**. No artificial value is filled.

### 10405 and 10306

10405's research canonicalizes to **ПК19**, which is unequal to **ПК19+20**.
It stays NO_GDI/count=0; no broadening of composite coverage.
10306 has only confirmed INITIAL. Its suffixed source records do not create
history events. The new `GDI_UNCONFIRMED_LIFECYCLE_RECORDS` warning gives physical
root, conflicting family, record count, dates and plast summary with source
locations. Current count=0, status=NO_GDI. Customer question is recorded in
OPEN_QUESTIONS.md; no automatic question or guessed ZBS was introduced.

## GDM lifecycle-family resolution

GDM now calls the same `resolve_lifecycle_stage` as GDI, with the source identity,
plast and study date. Raw equality is no prerequisite. Synthetic annotated and
no-separator ZBS-family rows resolve to current ZBS3; explicit ZBS1/ZBS2 cannot
be borrowed by ZBS3. PVLG inheritance and GS/MZS separation stay constrained by
history. Missing/fallback/stale Delta tests preserve numeric zero/negative rules.
Production candidate rows **54 → 61**, stale fallbacks **16 → 17**; final GDM
values remain **5 Да / 45 Нет / 28 blank**. 112 keeps 2025-02-28 Delta ≈−1.35,
183-day fallback relative to latest 2025-08-30 research, result Нет. 10201 still
has no eligible finite current Delta. No cross-lifecycle reuse.

## Customer examples

| Well | v0.17 | v0.18 |
|---|---:|---:|
| 12 | 20 | 20 |
| 13 | 21 | 21 |
| 21 | 19 | 19 |
| 22 | 19 | 19 |

## Runtime inputs and criteria

| Role | Basename | Bytes | SHA-256 | Revalidation |
|---|---|---:|---|---|
| calculator | GDIS_Rating_Calculator_FIXED.xlsx | 1886651 | `bb046cc365749a546d1bbe141165b08a664ba427ab9493b678ddce008fc85c6a` | matched |
| fund | Фонд 2026 на 01.08.2026.xlsx | 2332175 | `0ee001ef1cc888492bccd29b11d565a7f0b9d5a64f9c2cfc805d47484f85eeb3` | matched |
| gdi | Сводная таблица ГДИ.xlsx | 3528428 | `2a25663622976f86237be2e1ab8507ae1de189cc83763b70774cc3f245c32d5c` | matched |
| lha | База ЛХА_Итог!.xlsm | 68924956 | `df4062ca25bb6c30e37150f85d56e084f4cbfe28064e4dfa497c32cc46a09bc8` | matched |
| well_history | База по скважинам.xlsx | 542744 | `7e2214316b87067ef2a1da412ac540fe76ac21ad6bf0be620b74311872518dfb` | matched |
| research_status | Статус исследований_2026.xlsx | 5810120 | `af83ddcfe3510f20d4414f5f00d33ba777baab885b3387ad51088d7b5ec1107a` | matched |
| daily_report | 07.2026 Cуточный рапорт БГП_полный.xlsm | 11237181 | `b41493b5b067b127d16fc68c9344e12eeff6d64be222aa67ce4af2fa9227ea4d` | matched |

Criteria source: **defaults**. Snapshot:

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

Runtime and audit timestamps/commit/tag remain distinct. Strict audit reopens
actual runtime paths, validates basename/size/SHA-256, fails on missing file or
changed bytes (including same basename). It never updates saved hashes.
Known runtime/audit commit and tag mismatch still fail. Internal paths and full
runtime reports/logs never enter audit manifest or archive. Developer non-strict
mode explicitly records unavailable/not_revalidated, never silently PASS.

## OOXML and deferred scope

Exactly **78 target rows**, `tblData=A6:Z84`, managed CF `A7:A84` (the existing
single-cell CF `G15` is retained). No stale target rows beyond row 84.
Only `xl/worksheets/sheet3.xml` and `xl/tables/table2.xml` differ; every other ZIP
entry is byte-identical. x14ac and mc:Ignorable are preserved. No changes to
Расчет, Рейтинг, Настройки, μ/λ, weights or calculation settings.
Structural formula migration remains deferred. Synthetic and real-source tests
cover the corrective behavior; CI skips production integration when data absent.
