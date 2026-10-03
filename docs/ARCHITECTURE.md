# Архитектура gdis_loader

## Назначение и ограничения

Загрузчик проверяет набор входных файлов, обнаруживает месторождения по фонду и
обновляет только лист `Данные` для одного явно выбранного месторождения. Текущие
правила зафиксированы в [`CUSTOMER_DECISIONS.md`](CUSTOMER_DECISIONS.md).

Writer читает схему через `openpyxl`, затем копирует исходный ZIP и патчит только
XML листа `Данные` и связанный XML `tblData`. Формулы, настройки и остальные листы
не мигрируют автоматически.

## Поток данных

```text
source workbooks -> readers -> typed domain -> normalization -> lifecycle match
                 -> transforms + immutable criteria snapshot -> report/diagnostics
                 -> OOXML patch: Данные + tblData
```

`validate` проверяет только inputs, discovers canonical fields from current fund,
and reports coverage. Он не проверяет output path и не пишет в output directory.
`update` требует explicit field; непосредственно перед записью валидирует
extension, конфликт с input и policy каталога результата.

Readers сохраняют исходные ячейки и provenance. Валидация и update используют
один `calculation_date` на запуск. MONTH и YEAR сохраняют исходную precision,
а расчётная effective date соответствует 1-му числу месяца / 1 января.

## Identity и lifecycle

`base_well_id` — физический root только для lineage поиска. Target identity
включает field, root, lifecycle stage и canonical plast. `ЗБС`, `ПВЛГ`, `ПНЛГ`
начинают новую history; `ПВР`, `КЛК` и прочие ГТМ не начинают. Перевод после
`ПВЛГ`/`ПНЛГ` сохраняет подтвержденную parent identity (включая ordinal ЗБС); lifecycle
history при этом остаётся отдельной и влияет на дату запуска, ГДИ, ЛХА, ГДМ и
производные значения.
Последовательные current ЗБС получают детерминированные ordinals по fund и
history. `ГС`/`МЗС` остаются отдельными histories. Ambiguous assignment не
угадывается.

Plast canonicalizer — чистый parser: NFKC, separator/space normalization,
основной номер слоя без sub-index, stable composites. Fuzzy matching отсутствует.

## GDI и transformations

Classifier принимает только normalized prefixes `ИД+КВД`, `ИД`, `КВД` в этом
порядке. Сuffix words не меняют классификацию; substring matches не используются.
Exact duplicate fingerprint включает все business attributes, но исключает
source coordinates/provenance; duplicate provenance объединяется.

После matching/plast normalization/launch defaulting/dedupe `Количество ГДИ`
считает valid rows с effective date `>= launch`. Productivity сравнивает numeric
`a` только на valid GDI rows. GDM selection ограничена current field/lifecycle/
plast и выбирает latest valid Delta либо fallback в пределах config window; Delta
между собой не сравнивается. Debit берет positive/above-threshold daily values
из месяца источника и усредняет их.

## Criteria config, GUI и отчет

`config.toml -> validated immutable CriteriaConfig -> snapshot на начало update`
является единственным путём числовых thresholds в business transforms. Отсутствие
criteria секций означает defaults; present invalid value блокирует безопасное
обновление и показывается пользователю. UI `Критерии…` редактирует только
значения и атомарно сохраняет их, сохраняя остальные config sections. Criteria
change не инвалидирует source validation; следующий update получает новый
snapshot.

JSON report сохраняет selected field, calculation date, config source, точные
criteria/defaults/origins, агрегаты и diagnostics. Не добавляет production row
dumps.

## Missing values и formula boundary

Качественные source fields при insufficient input остаются blank/unknown, не
превращаются в `Нет`. По бизнес-правилу `μi` должен быть `0`, а критерий должен
быть исключён из final `λ`. Формулы текущего workbook это правило не обеспечивают
полностью: `Критерии`
формирует текст `Недостаточно данных`, а `Расчет!J` оставляет `λ` пустым при
наличии такой строки. Исправление требует отдельной structural/formula migration;
этот release её не делает. См. `STRUCTURAL_CALCULATOR_MIGRATION.md`.

## Safe write, GUI и release

Output path проверяется только для update; `validate` не создаёт каталоги и не
зависит от пути результата. GUI combo остается пустым до успешной проверки и не
делает auto-selection. Input path change invalidates discovery; output/criteria
change не invalidates. Progress достигает 100 только при успехе.

Каждая операция создаёт text log и JSON report. Windows release использует
GitHub Actions, Python 3.14, `uv sync --locked`, quality checks, PyInstaller
`onedir`, frozen version smoke-test и автоматически тегируется только после
успешного push в `main`.


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
