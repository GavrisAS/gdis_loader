# Production reconciliation v0.13

Проверка выполнена 2026-10-02 на текущем полном bundle из `data/`. В Git не
попали source files, созданный калькулятор, JSON report или runtime log. В этом
документе только агрегаты и четыре customer examples.

## Discovery и фонд

`validate` обнаружил поля из фонда и не выбирал target автоматически:

| Месторождение | Фонд | ГДИ rows | ЛХА rows | History rows | GDM status rows |
|---|---:|---:|---:|---:|---:|
| Береговое | 109 | 1,832 | 3,432 | 123 | 769 |
| Пырейное | 9 | 131 | 383 | 26 | 53 |
| Хадырьяхинское | 11 | 204 | 256 | 28 | 75 |

Для выбранного Берегового: 109 fund rows, 78 eligible, 31 excluded. В target
записано 78 строк. Из них 69 lifecycle/GDI matches однозначны, 9 остаются
ambiguous; `no_gdi=0`, `invalid_source=0`. Output не превышает 100 строк capacity
расчетных листов.

## ГДИ и полный count reconciliation

Для Берегового прочитано 1,832 raw source rows; exact dedupe оставил 1,830 и
схлопнул 2 повтора с `GDI_EXACT_DUPLICATE_COLLAPSED`.

| Класс | Raw | После dedupe |
|---|---:|---:|
| ID | 32 | 32 |
| ID_KVD | 867 | 866 |
| KVD | 701 | 701 |
| EXCLUDED | 209 | 208 |
| UNKNOWN | 23 | 23 |

Raw valid GDI — 1,600; deduplicated valid GDI — 1,599. Prefix-negative labels
включали: `Pст` 168, `Замер Рпл` 36, `КВУ` 9, `длит.остановка` 5, пустые 4,
`ПГИ` 4, `Рстатика, запуск в экспл` 3, `МГРП освоение` 1, `МЗС+миниКВД` 1,
`Рпл` 1. В частности `МЗС+миниКВД` не попал в valid KVD.

`scripts/reconcile_gdi.py` выполнил cross-check всего eligible Берегового фонда
с повторным чтением count cells калькулятора. Lifecycle resolver, normalization,
matching, classification и dedupe используют общие canonical production
primitives, поэтому эту проверку нельзя называть полностью независимой:
69 resolved rows проверены against deduplicated current lifecycle/plast records;
9 unresolved rows оставлены вне прямого per-identity сравнения. На 69 resolved
rows число несовпадений с колонкой `Количество ГДИ` равно **0**.

В reconciliation для resolved current lifecycle/plast: 769 raw valid rows;
после dedupe 768, включая 16 до launch, 751 после launch и 1 запись без даты.
Итого в target count вошли 751 valid unique post-launch GDI across resolved
identities. Другие lifecycle/plast и invalid kinds не включаются.

### Customer examples

| Скважина | Effective launch | До запуска | После запуска, unique | Первая после launch | В калькуляторе | Итог |
|---|---|---:|---:|---|---:|---|
| 12 | 01.02.2008 | 1 | 20 | 17.06.2008 | 20 | PASS; запись 06.06.2002 исключена как pre-launch |
| 13 | 01.05.2002 | 0 | 21 | 27.05.2002 | 21 | PASS |
| 21 | 01.03.2004 | 0 | 19 | 11.03.2004 | 19 | PASS |
| 22 | 01.03.2004 | 0 | 19 | 01.04.2004 | 19 | PASS; off-by-one не обнаружен |

Для 22 первая релевантная строка начинается 01.04.2004, после effective launch;
все 19 уникальных valid GDI после запуска присутствуют в итоговом count. Новое
правило исправило same-month boundary для 13 и 21, не подгоняя результат 22.

## Даты, lifecycle и пласты

В базе истории прочитано 123 records и 69 GTM events: ЗБС 55, ПВЛГ 8, ПВР 5,
OTHER 1; PNLG event в этой production выборке нет. Для source dates зафиксировано
DAY 3 и MONTH 187. В выбранном target launch заполнен для 72 строк; 71 effective
date достроена по customer rule, 6 launch dates отсутствуют, incomplete precision
не осталось. Raw precision/defaulting rule записаны отдельно от effective date.

В GDI Берегового получено 28 canonical plast labels; 129 строк имеют composite
основных пластов. Canonicalizer убирает sublayer suffix, в том числе согласно
примерам заказчика `ПК17-2-1 -> ПК17` и `ПК14-1 -> ПК14`; composites приводятся к
основным слоям и стабильному порядку. Это не вводило fuzzy matching: остаются 18
`UNRESOLVED_PLAST_EQUIVALENCE` diagnostics, поэтому неподтвержденная эквивалентность
не назначалась автоматически. Пять suffixless GDI assignments подтверждены
однозначной историей.

Lifecycle diagnostics: 9 `GDI_AMBIGUOUS_MATCH`, 16 `WELL_HISTORY_STAGE_AMBIGUOUS`
и 2 `WELL_HISTORY_STAGE_NOT_FOUND` issue instances. Такие rows не разрешались
случайным выбором.

## GDM

Прочитано 769 status rows: 515 finite numeric Delta, 2 invalid, 252 missing,
0 formula rows without cached numeric result. 152 строки были per-row candidate
при `abs(Delta)>5`.

По 69 однозначным target identities: `Проблемы ГДМ` — Да 4, Нет 45, blank 20.
На текущие target lifecycle/plast mapped 54 per-row candidates. Выбрано 11 fallback
Delta; 16 предыдущих значений отвергнуты как старше 365 дней. Explicit-suffix
status rows также проверяются через lifecycle date interval, поэтому старые rows
не переиспользуются только из-за совпадения suffix.
Разные Delta между датами не вычитались и не сравнивались. Использовались все
типы relevant research rows. 18 plast-equivalence diagnostics и unresolved
identities объясняют часть blank значений без переноса старого пласта/history.

## Дебит и остальные target fields

Средний debit записан для 57 строк; 12 rows оставлены blank из-за неоднозначной
field assignment в daily source. Для заполненных средних использовано 1,355
valid working-day values (numeric и строго `>0`). Другие поля/месторождения не
подмешивались. Daily source не всегда содержит canonical field label, поэтому
совпадение well number само по себе недостаточно.

Число заполненных значений в `Данные` (из 78 target rows):

| Поле | Filled |
|---|---:|
| Скважина / Состояние / ГТМ | 78 / 78 / 78 |
| Пласт | 72 |
| Дата запуска | 72 |
| Количество ГДИ / Недостаточно ГДИС | 69 / 69 (Да 1, Нет 68) |
| Глубинные датчики | 66 (Да 17, Нет 49; 3 unknown среди matched) |
| Снижение продуктивности | 61 |
| Рост хлора | 65 |
| Cl текущий / предыдущий | 67 / 65 |
| Проблемы ГДМ | 49 (Да 4, Нет 45) |
| ЛНД | 37 (Да 30, Нет 7; 32 unknown среди matched) |
| Продолжительность без ГДИ / ИД / КВД | 69 / 69 / 69 |
| Удельное количество ГДИ | 69 |
| ВГФ текущий / предыдущий | 67 / 67 |
| Дебит | 57 |

Остальные target blanks соответствуют insufficient inputs, unresolved matching,
или согласованным пока пустым полям. `ГТМ=Нет` остаётся временным решением.

## Criteria snapshot и diagnostics

Операция использовала локальную calculation date `2026-10-02`. Все значения были
defaults (config source — `config.toml`):

```text
insufficient_gdi_min_count       = 2
productivity_min_increase        = 0.0
chlorine_current_min_mg_dm3      = 2000.0
chlorine_delta_min_mg_dm3        = 1000.0
downhole_depth_threshold_m       = 0.0
gdm_abs_delta_threshold          = 5.0
gdm_fallback_max_age_days        = 365
gas_rate_working_day_min_rate    = 0.0
```

Отчёт содержит criteria snapshot и `default` origin для каждого значения. Run
завершился с 0 errors, 155 warnings и 308 info diagnostics. Среди INFO включены
два exact duplicate collapse, 71 customer date defaulting и 170 LHA duplicate
maximum resolutions. Diagnostics сохраняют source provenance без production
row dump в этом документе.

## OOXML invariants и формульный слой

Исходная и итоговая книги имеют по 27 ZIP entries и одинаковый набор имён.
Байт-в-байт изменились только:

```text
xl/worksheets/sheet3.xml   (лист Данные)
xl/tables/table2.xml       (tblData)
```

`tblData=A6:Z84`; conditional formatting `A7:A84`; namespace marker `x14ac` в
XML листа `Данные` сохранён. Все остальные ZIP entries, включая остальные sheets,
styles, formulas, relationships и calc metadata, побайтно идентичны.

Raw semantics loader реализована: неизвестные quality inputs остаются blank.
Formula-level behavior **не** обеспечивает `μ=0` плюс исключение конкретного
criterion из final `λ`: действующая активная строка `Не проведен АДД` указывает
на пустую колонку, `Критерии` формирует `Недостаточно данных`, а `Расчет!J`
оставляет λ blank при такой отметке. Требуется отдельная approved structural
migration; в v0.13 workbook formulas не менялись. Подробности — в
[`STRUCTURAL_CALCULATOR_MIGRATION.md`](STRUCTURAL_CALCULATOR_MIGRATION.md).
