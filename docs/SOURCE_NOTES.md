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
  рассчитывается. Fallback window 365 дней — project interpretation, не blocker.

## База ЛХА и суточный рапорт

- ЛХА использует лист `БД Сибнефтегаз`, field/well/plast/timestamp/Cl/VGF. Для
  одинаковых metric+timestamp берётся максимум valid numeric value; в этом run
  разрешено 170 duplicate groups. Ноль остаётся числом.
- Суточный рапорт использует лист `Добыча телеметрия`; дневные колонки читаются
  за месяц. Working-day rule: numeric rate строго больше configurable threshold,
  default 0; среднее арифметическое по валидным дням. В июльском production
  bundle нашли 121 telemetry row. Источник не всегда даёт однозначный field
  assignment; 12 target rows оставили Debit blank с diagnostic.
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
