# Маппинг листа `Данные`

`validate` обнаруживает fields из актуального фонда и показывает source coverage.
`update` принимает только явно выбранное field и пишет eligible rows выбранного
field. В `Данные` не добавляется колонка месторождения. Customer rules находятся
в [`CUSTOMER_DECISIONS.md`](CUSTOMER_DECISIONS.md).

Для production Берегового: 109 fund rows, 78 eligible, 31 excluded. Target — 78
строк; в отчётном period eligible categories — дающие, дающие газ и остановленные
в отчётном месяце/периоде.

| Поле `Данные` | Статус | Источник / правило |
|---|---|---|
| Скважина | заполняется | Current lifecycle display identity; PVLG/PNLG use `physical_root` without source suffix while retaining separate histories; unresolved match — blank. |
| Пласт | заполняется | Current normalized primary plast/composite; source raw сохранён в provenance. |
| Состояние | заполняется | Eligible fund category, normalized to `Дающие газ` or `Остановленные в отчетном периоде`. |
| Дата запуска | условно | DAY unchanged; MONTH → first of month; YEAR → Jan 1. Effective date and defaulting provenance both recorded. |
| Количество ГДИ | условно | Deduplicated valid prefix-classified GDI after effective launch, current lifecycle and plast only. |
| Глубинные датчики | условно | Latest valid GDI depth `> depth_threshold_m` → Да, otherwise Нет; missing/invalid blank. Default threshold 0. |
| Расходомер | пусто | Deferred to structural calculator migration. |
| ГТМ | временно заполняется | `Нет` until a plan source is supplied. |
| Недостаточно ГДИС | условно | `count < min_count` → Да; otherwise Нет. Default `min_count=2`. Unresolved identity blank. |
| Снижение продуктивности | условно | Last two valid current GDI rows with numeric `a`; delta strictly greater than configured `min_increase` → Да, otherwise Нет. Default 0. Missing pair blank. |
| Рост хлора | условно | Current Cl strictly over configured threshold and strict increase over previous Cl. Defaults 2000 and 1000 mg/dm³. Missing pair blank. |
| Cl текущий / предыдущий | условно | Latest two LHA points in current history. Duplicate metric/timestamp uses maximum finite numeric value; otherwise source blanks remain blank. |
| Проблемы ГДМ | условно | Latest relevant valid Delta, with previous valid fallback up to configured age. `abs(Delta) > threshold` → Да, otherwise Нет; missing selected Delta blank. |
| ЛНД | условно | Existing confirmed tri-state rule: Да when reliability is low or RFP says no; Нет only when both values are present/recognized and positive condition is false; otherwise blank. |
| Последний АДД / Не проведен АДД | пусто | Deferred to structural calculator migration. |
| Продолжительность без ГДИ | условно | From latest valid GDI; if none, from effective launch. Actual days / 365. |
| Удельное количество ГДИ | условно | `((calculation_date-launch_date).days/365)/count` for count > 0. Source cell blank at count 0. |
| ВГФ текущий / предыдущий | условно | Same lifecycle-safe LHA selection and duplicate maximum rule as Cl. |
| Продолжительность без ИД | условно | From latest ID/ID_KVD; if absent, from effective launch. Actual days / 365. |
| Продолжительность без КВД | условно | From latest KVD/ID_KVD; if absent, from effective launch. Actual days / 365. |
| Техническая возможность | пусто | Deferred to structural calculator migration. |
| Дебит | условно | Arithmetic mean of monthly daily numeric values strictly greater than `working_day_min_rate`; default 0. No valid days or ambiguous source field — blank. |
| Manual μ | пусто | Manual input; never calculated by loader. |

Missing input for a qualitative field stays blank and carries diagnostics. Its
business meaning for a future formula migration is `μ=0` and exclusion of that
criterion from final `λ`. The current calculator formula gap is documented in
[`STRUCTURAL_CALCULATOR_MIGRATION.md`](STRUCTURAL_CALCULATOR_MIGRATION.md).

The production v0.14 corrective regression, 12/13/21/22 reconciliation, fill
counts and OOXML checks are recorded in
[`REAL_DATA_DELTA_v0.14.md`](REAL_DATA_DELTA_v0.14.md); the original v0.13 run is
retained in [`REAL_DATA_DELTA_v0.13.md`](REAL_DATA_DELTA_v0.13.md).


## Corrective pass v0.17: well-id grammar

Общий `normalize_well_id` используется фондом, ГДИ, ГДМ (research status),
ЛХА, history и daily readers. Parser извлекает physical root (`base_well_id`),
family (`recognized_variant`), `ordinal`, `annotation` и `raw`.
Для известных markers поддержаны `_`, пробел, дефис и отсутствие разделителя:
`112збс -> 112_ЗБС`, `10404збс2 -> 10404_ЗБС2`, `54ГС -> 54_ГС`.
ГС/МЗС остаются отдельными identities; неизвестный текст не угадывается.

Bare ЗБС означает ordinal 1 только в конце строки. Explicit `ЗБС1`, `ЗБС 1`
canonicalize в `_ЗБС`; ordinal 2+ сохраняется. Аннотированные `_ЗБС_МГРП`,
`ЗБС МГРП`, `_ЗБС_ПИЛОТ2`, `_ЗБС(ГС1+ГС2)` имеют family ЗБС,
**ordinal=None**, сохраняют annotation и не становятся `_ЗБС`.
ГДИ такой family назначается по confirmed timeline, field, plast, date и fund
scope; suffix не выбирает ЗБС1. До первой ЗБС либо при конфликте assignment
не выполняется. PVLG/PNLG inheritance, separate GS/MZS, NO_GDI и independent
Debit/GDM/LHA semantics сохраняются.

Сверка production и aggregate inventory: [REAL_DATA_DELTA_v0.17.md](REAL_DATA_DELTA_v0.17.md).

## Underscore exact-plast syntax (v0.19)

`ПК_1 → ПК1`; `ПК20_2`, `ПК20_0_1 → ПК20`;
`ПК19_1+2`, `ПК19_2+1? → ПК19`. Underscore после primary обозначает
sublayer detail. Замена `_` для произвольных строк не выполняется.
`ПК19-20`, `ПК19-2+20`, `ПК19/2+ПК20`, `ПК19-ПК20 → ПК19+20`;
`ПК14+15` остается составным. Exact single primary не равен joint plast.
`Береговой (ПК9-17)` по-прежнему fund range, не exact composite.
