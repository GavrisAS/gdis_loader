# Production regression v0.15

Проверка выполнена на доступном production bundle из `data/`: selected field
`Береговое`, `calculation_date=2026-10-02`, `fund_date=2026-08-01`, default
`CriteriaConfig`. v0.14 baseline и исправленный output сформированы теми же
исходниками, калькулятором и датой расчёта. В этом документе приведены только
агрегаты и четыре согласованных customer examples; production row dumps не
включены.

## Inputs и manifest

Все перечисленные источники имели статус `available`. SHA-256 рассчитан по
исходным байтам. Имена — только basename; абсолютные пути не записываются.
Полный машиночитаемый manifest с размером, полным SHA-256, timestamp, commit,
release tag, Python, датой расчёта и selected field приложен к audit bundle как
`SOURCE_MANIFEST.json`.

| Role | Файл | Bytes | SHA-256 |
|---|---|---:|---|
| calculator | `GDIS_Rating_Calculator_FIXED.xlsx` | 1,886,651 | `bb046cc365749a546d1bbe141165b08a664ba427ab9493b678ddce008fc85c6a` |
| fund | `Фонд 2026 на 01.08.2026.xlsx` | 2,332,175 | `0ee001ef1cc888492bccd29b11d565a7f0b9d5a64f9c2cfc805d47484f85eeb3` |
| gdi | `Сводная таблица ГДИ.xlsx` | 3,528,428 | `2a25663622976f86237be2e1ab8507ae1de189cc83763b70774cc3f245c32d5c` |
| lha | `База ЛХА_Итог!.xlsm` | 68,924,956 | `df4062ca25bb6c30e37150f85d56e084f4cbfe28064e4dfa497c32cc46a09bc8` |
| well_history | `База по скважинам.xlsx` | 542,744 | `7e2214316b87067ef2a1da412ac540fe76ac21ad6bf0be620b74311872518dfb` |
| research_status | `Статус исследований_2026.xlsx` | 5,810,120 | `af83ddcfe3510f20d4414f5f00d33ba777baab885b3387ad51088d7b5ec1107a` |
| daily_report | `07.2026 Cуточный рапорт БГП_полный.xlsm` | 11,237,181 | `b41493b5b067b127d16fc68c9344e12eeff6d64be222aa67ce4af2fa9227ea4d` |
| generated_calculator | `gdis_loader_v015_corrected.xlsx` | 1,341,789 | `80dd9a1c3d80f019a890c2585582700d6572debb6acd7bb88a6eab2f6498a1a9` |

Manifest содержит только metadata и digests. В audit bundle не копируются
production files, generated calculator, user config, runtime logs или JSON
отчёты с исходными данными.

## Fund и lifecycle

- В фонде всего 129 записей; 109 относятся к Береговому, из них 78 eligible
  target rows. Output содержит 78 строк.
- Строго по fund state + history resolver определил lifecycle у 61 из 78 rows;
  17 остались `AMBIGUOUS` из-за неразрешённой current lifecycle/plast identity.
- Из 78 строк 3 имеют определённую текущую lifecycle identity и не имеют
  валидного ГДИ в ней (`NO_GDI`). В v0.14 было 0.
- Cross-check count по canonical current stage identities: `INITIAL=44`,
  `ЗБС=24`, `ПВЛГ=3`, `ПНЛГ=0`. Это distinct identity counts, не разбиение
  78 fund rows. Для 10 из 17 строк со строгим unresolved результатом валидный
  GDI record cross-check подтверждает ровно одну latest timeline boundary;
  такие записи учитываются только в audit stage counts и не становятся
  eligible для output.

Canonical current PVLG identity — уникальный physical root среди eligible
Береговых target rows, у которого latest boundary stage на fund date — PVLG.
Сначала применяется прямое разрешение по fund plast и history. При конфликте
plast identity входит только в cross-check count, если валидная GDI запись
разрешается в ту же единственную latest boundary. Для этого набора найдено 3
таких PVLG roots: `54`, `10803`, `10601`. Предыдущий отчёт показывал 2 из-за
подсчёта по fund target display/grouping; в v0.15 исправлена reconciliation
группировка по physical root. Эта audit-only cross-check не меняет strict
eligibility loader.

## GDI и customer examples

- 1,832 raw rows; 1,830 после exact dedupe; схлопнуто 2 полных дубликата.
- 1,600 raw valid rows и 1,599 deduplicated valid rows по Береговому.
- Для разрешённых current lifecycle/plast: 693 deduplicated valid rows — 10 до
  effective launch, 682 после или на launch, одна строка без даты исключена из
  date-based count. Старые lifecycle/plast кандидаты не переносятся в текущую
  историю.
- Четыре утверждённых customer примера совпали с калькулятором: `12 → 20`,
  `13 → 21`, `21 → 19`, `22 → 19`. Application count mismatches: 0.

| Well | Launch | До launch | После launch | Calculator | Проверка |
|---|---|---:|---:|---:|---|
| 12 | 01.02.2008 | 1 | 20 | 20 | PASS |
| 13 | 01.05.2002 | 0 | 21 | 21 | PASS |
| 21 | 01.03.2004 | 0 | 19 | 19 | PASS |
| 22 | 01.03.2004 | 0 | 19 | 19 | PASS |

Cross-check использует production canonical lifecycle resolver, normalization,
matching, classification и duplicate collapse. Независимо реализованная часть —
повторное чтение count cells из output calculator и сравнение count values.
Поэтому это service/output cross-check, а не полностью независимая реализация
business rules.

## NO_GDI и производные поля

Во всех трёх `NO_GDI` rows: `Количество ГДИ=0`, `Недостаточно ГДИС=Да`, launch
date определена; длительности без ГДИ/ИД/КВД отсчитываются от этой даты.
`Удельное количество ГДИ`, ЛНД, глубинные датчики и снижение продуктивности
остались blank. Однозначные независимые источники продолжили работать: LHA
текущий Cl заполнен у 1 из 3, предыдущий Cl — у 0; GDM заполнен у 1; Debit — у
всех 3.

| Метрика | v0.14 | v0.15 |
|---|---:|---:|
| Match status: Matched / Ambiguous / NO_GDI | 69 / 9 / 0 | 58 / 17 / 3 |
| `Скважина` filled (values changed) | 78 (4) | 78 (4) |
| `Пласт` filled | 72 | 61 |
| `Состояние` / `ГТМ` filled | 78 / 78 | 78 / 78 |
| `Дата запуска` filled | 72 | 61 |
| `Количество ГДИ` filled | 69 | 61 |
| `Недостаточно ГДИС` filled (Да / Нет) | 69 (1 / 68) | 61 (3 / 58) |
| `Продолжительность без ГДИ` filled | 69 | 61 |
| `Продолжительность без ИД` / `без КВД` filled | 69 / 69 | 61 / 61 |
| `Удельное количество ГДИ` filled | 69 | 58 |
| `Глубинные датчики` / `ЛНД` filled | 66 / 37 | 55 / 31 |
| `Снижение продуктивности` filled | 61 | 55 |
| `Рост хлора` filled | 65 | 56 |
| `Cl текущий` / `Cl предыдущий` filled | 67 / 65 | 57 / 56 |
| `ВГФ текущий` / `ВГФ предыдущий` filled | 67 / 67 | 57 / 57 |
| `Проблемы ГДМ` filled (Да / Нет / blank) | 49 (4 / 45 / 20) | 46 (4 / 42 / 15) |
| `Дебит` filled / blank | 57 / 12 | 49 / 12 |
| Debit valid daily values | 1,355 | 1,175 |
| GDI valid rows исключены как pre-launch | 16 | 10 |

Из 78 rows 14 имеют одно или более отличающихся значений между output v0.14 и
v0.15; 4 ячейки `Скважина` отличаются. Из прежних 69 matched rows 11 больше не
используют старые lifecycle/plast candidates: 3 стали корректными `NO_GDI`, а
8 остались lifecycle-ambiguous. Остальные 9 ambiguous rows уже имели этот статус
в v0.14. Эти дельты следуют из запрета fallback в предыдущую lifecycle; старое
ГДИ больше не подменяет отсутствие текущего.

## OOXML

В v0.15 target rows — 78; `tblData=A6:Z84`; conditional formatting —
`A7:A84`; максимальная строка листа `Данные` — 84, stale rows отсутствуют.
Сравнение output с исходным calculator показало:

- изменены только `xl/worksheets/sheet3.xml` (лист `Данные`) и
  `xl/tables/table2.xml` (`tblData`);
- набор ZIP entries полностью совпадает;
- каждый нетаргетный ZIP entry byte-identical;
- `x14ac` и `mc:Ignorable` сохранены; formula sheets и остальные части книги
  неизменны.

Structural migration formula layer остаётся отложенной: листы `Расчет`,
`Рейтинг`, `Настройки`, критерии, веса и формулы не менялись.
