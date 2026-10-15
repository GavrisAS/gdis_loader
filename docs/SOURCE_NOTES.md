# Наблюдения о текущих источниках

Наблюдения обновлены для production bundle на 2026-10-02. Файлы `data/` не
включаются в Git. Бизнес-правила приведены в
[`CUSTOMER_DECISIONS.md`](CUSTOMER_DECISIONS.md); агрегированный результат v0.13 —
в [`REAL_DATA_DELTA_v0.13.md`](REAL_DATA_DELTA_v0.13.md).

## Калькулятор `GDIS_Rating_Calculator_FIXED.xlsx`

- Листы: `README`, `Настройки`, `Данные`, `Критерии`, `Расчет`, `Рейтинг`.
- Target headers расположены в строке 6; 26 колонок A:Z; данные с 7-й строки;
  таблица `tblData`, исходный ref `A6:Z106`.
- Writer изменяет только `xl/worksheets/sheet3.xml` (лист `Данные`) и
  `xl/tables/table2.xml` (`tblData`); остальная ZIP-книга копируется без
  перезаписи. Для 78 строк Берегового ожидаются ref `A6:Z84` и conditional
  formatting `A7:A84`.
- Formula layer условно распознаёт отсутствующий критерий как
  `Недостаточно данных`, а `Расчет!J` становится blank при таком результате.
  Поэтому blank source → μ=0 + исключение критерия из λ не реализуется текущими
  формулами; см. `STRUCTURAL_CALCULATOR_MIGRATION.md`.

## Фонд `Фонд 2026 на 01.08.2026.xlsx`

- Актуальный лист `01.08.2026`, дата фонда `2026-08-01`.
- Фонд содержит 129 строк: Береговое 109, Пырейное 9, Хадырьяхинское 11.
  Для Берегового 78 строк eligible и 31 исключена по статусам.
- Eligible: дающие, дающие газ, остановленные в отчетном периоде. Категории J
  («в освоении/ожидании») не включаются.
- Canonical mapping: `БЛУ -> Береговое`, `ПЛУ -> Пырейное`, `ХЛУ ->
  Хадырьяхинское`. Новые fields остаются в discovery с warning, если source
  mapping не настроен.
- Встречается `153 162`: разделять только при подтверждении ожидаемым count 2;
  INFO сохраняет исходную ячейку. Произвольные whitespace номера не разделять.

## `База по скважинам.xlsx`

- Текущие листы `БЛУ`, `ПЛУ`, `ХЛУ`; два ряда заголовков, повторяемые блоки ГТМ.
- В production прочитано 123 history records и 69 GTM events: 55 ЗБС, 8 ПВЛГ,
  5 ПВР и 1 прочее событие. В этой выборке даты имели исходную precision:
  DAY 3, MONTH 187. YEAR обработан parser rule и покрыт synthetic tests.
- Числовые даты интерпретируются с учётом number format. Raw precision остаётся
  в provenance; effective date строится по customer rule (MONTH -> day 1,
  YEAR -> Jan 1).

## Сводная таблица ГДИ

- Reader ищет semantic headers: field, well, plast, kind, date, depth, `a`, `b`,
  LND/RFP и другие доступные business values.
- Береговое: 1,832 raw rows, 1,830 после exact duplicate collapse (2 повтора).
  Raw prefix classes: EXCLUDED 209, ID 32, ID_KVD 867, KVD 701, UNKNOWN 23.
  После dedupe: EXCLUDED 208, ID 32, ID_KVD 866, KVD 701, UNKNOWN 23.
- Prefix marker определяет type; arbitrary trailing explanatory words допустимы.
  `МЗС+миниКВД` не распознаётся как KVD по substring.
- Cross-check full-fund reconciliation с общими canonical business primitives
  описан в `REAL_DATA_DELTA_v0.13.md`.

## `Статус исследований_2026.xlsx`

- Рабочие листы `АР_таблица_БЛУ`, `АР_таблица_ПЛУ`, `АР_таблица_ХЛУ`; чтение
  по field mapping.
- На Береговом прочитано 769 status rows: 515 finite numeric Delta, 2 invalid,
  252 missing; formula cache без numeric результата — 0. 152 rows проходят
  per-row `abs(Delta)>5` candidate threshold.
- Target selection сначала ограничивает field/current lifecycle/current
  normalized plast; все research kinds допустимы. Междатный Delta trend не
  рассчитывается. Окно v0.22: 730 дней включительно от calculation date, для любого выбранного Δ.

### Updated source audited for v0.22 (2026-10-07)

SHA-256: `a898ea4cd2e41d3e2dec91fd9685bba763bc8e22415022a0e74c0a78e950f1b0`.
Semantic columns: well A, plast B, kind C, study date D; Delta J in БЛУ,
I in ПЛУ/ХЛУ. Headers are merged across rows2–4; dates/years are in row values,
not separate year columns. The reader retains source precision and defaults partial
dates by the established customer rule. Undated/header remnants cannot be assigned
to a lifecycle and are excluded from selection.

| Used sheet | Parsed rows | Finite Delta | Dated years / row counts | Delta formulas |
|---|---:|---:|---|---:|
| АР_таблица_БЛУ | 769 | 515 | 2021:2, 2022:159, 2023:216, 2024:171, 2025:144, 2026:57 | 517 |
| АР_таблица_ПЛУ | 53 | 10 | 2022:8, 2023:15, 2024:21, 2025:7 | 10 |
| АР_таблица_ХЛУ | 75 | 59 | 2022:13, 2023:17, 2024:22, 2025:21 | 59 |

There are no Delta formulas without cached results. Two БЛУ formula results are
invalid; missing/dash/text/error values remain unknown. Other formulas are present
outside Delta. Several plasts per source identity occur for28/1/3 wells respectively;
ЗБС/ЗБС2, annotated ЗБС, ГС and ПВЛГ labels are present. AutoFilters remain;
no hidden rows in the updated sheets. Merged data cells are retained as sparse
source values, never filled across identities. БЛУ has inflated max_column16383;
the semantic reader limits its scan and reads only the detected required columns.

## База ЛХА и суточный рапорт

- ЛХА использует лист `БД Сибнефтегаз`, field/well/plast/timestamp/Cl/VGF. Для
  одинаковых metric+timestamp берётся максимум valid numeric value; в этом run
  разрешено 170 duplicate groups. Ноль остаётся числом.
- Для расчёта дебита основной источник — `09.2026 Cуточный рапорт БГП.xlsm`,
  лист `Добыча телеметрия` (case-insensitive exact sheet match). Заголовки имеют
  31 дневную колонку, но проверенные датированные вкладки `01`–`30` подтверждают
  сентябрь 2026; колонка 31 исключается. В 121 telemetry rows колонка `ГСК`
  обозначает номер газосборного коллектора, а не месторождение. Field scope
  подтверждается прямыми формулами ссылок на строки датированных дневных листов,
  заголовком промысла, датой и совпавшими well identities. Для cache-less formulas
  значения остаются missing. Агрегация сохраняет действующее среднее числовых
  дневных ставок строго выше configurable threshold, default 0. Production
  reconciliation v0.24 — локально в ignored `artifacts/v0.24/reconciliation.json`;
  он использует только сентябрьский источник. Июльский рапорт относится к
  историческому запуску v0.23 и не является текущим источником.
- Ошибки/пустые/служебные values не включаются в среднее; данные источника не
  изменяются.

## Реальные файлы и synthetic tests

Production files находятся в ignored `data/`. Integration tests автоматически
пропускаются, когда полного bundle нет. CI использует synthetic workbooks без
production rows. В документации записываются только агрегаты и разрешённые
customer examples.


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

## Production underscore inventory (v0.19)

All seven source roles/all worksheets were scanned: history has 13 `ПК_1`
cells; LHA has 60 `ПК20_2` cells; research status has 2 `ПК20_0_1` cells.
Other roles have no underscore ПК cells. Shared normalization maps these to
ПК1/ПК20/ПК20. Пырейное eligible 22/62 now resolve INITIAL, counts 11/4.
Хадырьяхинское has 10 eligible rows and no output delta; raw historical forms
remain meaningful test coverage. Full scope/coverage and field aggregates:
[REAL_DATA_DELTA_v0.19.md](REAL_DATA_DELTA_v0.19.md).
