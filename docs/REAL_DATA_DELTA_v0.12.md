# Агрегированный real-data delta для v0.12

Производственные файлы и построчные выгрузки в документ не включены. Прогон выполнен `2026-10-01` (локальная дата операции) по текущему production bundle. Историческая база сравнения — [`REAL_DATA_DELTA_v0.11.md`](REAL_DATA_DELTA_v0.11.md); знаменатели отличаются из-за фильтра фонда по подтвержденной eligibility.

## Field discovery и фонд

`validate` завершился без ERROR и обнаружил поля из фонда:

| Canonical field | Строк фонда | ГДИ | ЛХА | История: лист / строк | Статус исследований: лист / строк |
|---|---:|---:|---:|---:|---:|
| Береговое | 109 | 1832 | 3432 | есть / 123 | есть / 769 |
| Пырейное | 9 | 131 | 383 | есть / 26 | есть / 53 |
| Хадырьяхинское | 11 | 204 | 256 | есть / 28 | есть / 75 |

Всего прочитано 129 строк фонда. Для выбранного regression scope `Береговое`: 109 до eligibility, 78 eligible target rows, 31 исключена (16 бездействующих текущего года и 15 бездействующих прошлых лет). Из eligible строк 75 относятся к нормализованной группе `Дающие газ`, 3 — к остановленным в отчетном периоде. `Данные` содержит 78 строк.

## Lifecycle и сопоставление

Для 78 выбранных target rows: `MATCHED=62`, `AMBIGUOUS=16`, `NO_GDI=0`. Три root-only записи ГДИ были assigned lifecycle stage по истории при однозначных дате и точном пласте. Остались 16 target ambiguity; важные issue counts: `GDI_AMBIGUOUS_MATCH=16`, `WELL_HISTORY_STAGE_AMBIGUOUS=33` locations/diagnostics, `UNRESOLVED_PLAST_EQUIVALENCE=24`, `WELL_HISTORY_STAGE_NOT_FOUND=3`. Эти diagnostic counts могут пересекаться и не суммируются в число скважин. Сопоставление по unresolved plast equivalence остается заблокированным; fuzzy equivalence не добавлялась.

В v0.11 scope составлял 109 строк: 84 matched и 25 ambiguous. Текущие 78 строк — только подтвержденный добывающий фонд; поэтому сравнение lifecycle totals не является тем же знаменателем. Разница 109 → 78 объясняется статусами фонда; текущий отчет отдельно фиксирует 3 root-only assignments и 16 ambiguous identities в выбранном scope.

## Классификатор ГДИ

Для всех 1832 строк Берегового:

| Класс | До fix, v0.11 | После fix, v0.12 |
|---|---:|---:|
| ID | 33 | 32 |
| ID_KVD | 866 | 867 |
| KVD | 695 | 702 |
| EXCLUDED | 209 | 209 |
| UNKNOWN | 29 | 22 |

После fix неизвестными остались 22 строки. `КВДгл`, `КВДстатика`, `МЗС+миниКВД` распознаны как KVD; `ИД+КВДсм НКТ` — как ID_KVD. Валидность определяется только классами ID/ID_KVD/KVD и не зависит от глубины. `ID_KVD` — одна запись в общем количестве, входящая в обе длительностные группы.

## Заполнение target fields

Среди 78 строк Берегового:

| Поле | Заполнено | Значения / причины пустых |
|---|---:|---|
| Состояние | 78 | 75 `Дающие газ`, 3 `Остановленные в отчетном периоде` |
| Дата запуска | 0 | 67 MONTH/YEAR precision, 11 missing; синтетический день не создавался |
| Количество ГДИ | 62 | 16 blank из-за lifecycle ambiguity |
| Недостаточно ГДИС | 62 | 0 `Да`, 62 `Нет`; 16 blank из-за lifecycle ambiguity |
| Снижение продуктивности | 56 | 6 без двух usable numeric `a`, 16 lifecycle ambiguous |
| Рост хлора | 56 | 6 без двух usable Cl точек, 16 lifecycle ambiguous |
| ЛНД | 34 | `Да=28`, `Нет=6`; 28 missing/unrecognized source outcomes и 16 ambiguous оставлены blank |
| Глубинные датчики | 59 | `Да=15`, `Нет=44`; 3 missing/invalid depth и 16 ambiguous оставлены blank |
| Продолжительность без ГДИ | 62 | последняя валидная ГДИ известна для каждой matched identity |
| Продолжительность без ИД | 60 | 2 matched identity без ID/ID_KVD и 16 ambiguous оставлены blank |
| Продолжительность без КВД | 62 | последняя валидная КВД/ID_KVD известна для каждой matched identity |
| Удельное количество ГДИ | 0 | ни у одной строки нет подтвержденной точной launch DAY; count=0 не подменялся искусственным нулем |

Дополнительно заполнены: `Скважина=78`, `Пласт=62`, `ГТМ=78` (временное правило `Нет`), `Cl текущий=56`, `Cl предыдущий=56`, `ВГФ текущий=57`, `ВГФ предыдущий=55`. `Расходомер`, `Проблемы ГДМ`, АДД-поля, `Техническая возможность`, `Дебит`, `Manual μ` оставлены пустыми по решениям/блокерам заказчика.

В v0.11 до eligibility-фильтра аудит показывал для LND `Да=42/Нет=6/UNKNOWN=36`, для глубинности `Да=18/Нет=64/UNKNOWN=2`. Текущие 78 eligible rows и исправленный classifier/lifecycle меняют знаменатель; target counts приведены выше из финального JSON report.

## Статус исследований / ГДМ

Для листа `АР_таблица_БЛУ`:

- 769 строк; 515 numeric Delta, 2 invalid, 252 blank/dash, 0 формул без cached numeric value;
- 152 строки имеют `abs(Delta) > 5` и являются candidate rows;
- в полном листе candidates относятся к 70 target identities; у 42 identities больше одной candidate row;
- в выбранном Береговом update matched к lifecycle target 49 candidate rows для 23 identities, из них у 11 identities несколько candidate rows.

`Проблемы ГДМ` оставлено пустым во всех target rows. Актуальная строка и fallback для invalid/latest Delta зависят от вопроса v2 №9. Candidate matching использует exact plast и temporal lifecycle; неоднозначность не разрешается fuzzy matching.

## Validation, diagnostics и OOXML

Validation: 0 ERROR, 31 WARNING. Update: 0 ERROR, 242 WARNING. Повторяющиеся source-shape diagnostics агрегированы; issue locations сохраняют provenance. Для LHA разрешено 139 совпадающих metric/timestamp групп правилом `max(valid numeric)` и INFO diagnostic.

В результате `GDIS_Rating_Calculator_FIXED_UPDATED_Береговое.xlsx` записано 78 строк. `tblData=A6:Z84`; conditional formatting покрывает `A7:A84`; `x14ac` сохранен. Ровно два ZIP entries отличаются от исходного калькулятора: `xl/worksheets/sheet3.xml` (лист `Данные`) и `xl/tables/table2.xml` (`tblData`). Добавленных/удаленных entries нет; остальные entries byte-identical, stale rows ниже таблицы отсутствуют.

## Открытые решения

Реализация не угадывает ответы v2: exact day для MONTH-only, роли ПВР/КЛК/прочих ГТМ, именование последовательных ЗБС, equivalence пластов, семантику `ГС`, длительности без ID/KVD при отсутствии истории, definition рабочего дня, missing-data policy и актуальную строку статуса ГДМ. Полный список остается в [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).
