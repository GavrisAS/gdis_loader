# Наблюдения о текущих источниках

Факты ниже получены по production-файлам к итерации v1.1. Файлы не включаются в
Git; актуальные правила заказчика описаны в
[`CUSTOMER_DECISIONS.md`](CUSTOMER_DECISIONS.md).

## Калькулятор `GDIS_Rating_Calculator_FIXED.xlsx`

- Единственный target sheet — `Данные`; headers в строке 6, данные с 7-й строки.
- 26 колонок A:Z; таблица `tblData`; исходный ref `A6:Z106`.
- OOXML writer сохраняет исходный ZIP и заменяет только XML листа `Данные` и
  XML `tblData`. Проверить byte identity остальных entries при update.
- Для Берегового regression после eligibility: 78 строк, `tblData=A6:Z84`,
  conditional formatting `A7:A84`.

## Фонд `Фонд 2026 на 01.08.2026.xlsx`

- Актуальный датированный лист `01.08.2026`, дата фонда в `C1`.
- Источник строк — группы C/D/G/H; J («в освоении/ожидании») не входит в фонд.
- Схема матричная: количество группы и список скважин расположены на соседних
  строках. Встречается `153 162`; разделять только при подтверждении ожидаемым
  количеством, сохраняя INFO provenance.
- Чтение последнего датированного листа обнаруживает текущие поля
  Береговое/Пырейное/Хадырьяхинское. Контрольный объем — 129 строк: Береговое
  109, Пырейное 9, Хадырьяхинское 11. Текущие 78 из 109 строк Берегового
  проходят eligibility, 31 не проходит.
- `Береговой`, `Пырейный`, `Хадырьяхинский` нормализуются в canonical
  `Береговое`, `Пырейное`, `Хадырьяхинское`. Новые имена из фонда остаются в
  discovery с диагностикой о ненастроенном source-sheet mapping.

## `База по скважинам.xlsx`

- Двухстрочные заголовки. Известные листы: `БЛУ`, `ПЛУ`, `ХЛУ`.
- Основные поля: куст, скважина, ВНС, пласт, информация, заканчивание,
  примечание. GTM blocks имеют повторяемый шаблон из шести колонок; reader
  находит блоки по header, а не фиксированному количеству.
- Raw values сохраняются вместе с addresses provenance. Hyperlink target не
  используется вместо значения ячейки.
- Даты бывают DAY, MONTH/YEAR и YEAR; числовые даты интерпретируются с учетом
  number format. Для MONTH/YEAR день не синтезируется.
- Lifecycle mapping — `БЛУ -> Береговое`, `ПЛУ -> Пырейное`,
  `ХЛУ -> Хадырьяхинское`. Это source mapping, а не список GUI.

## Сводная таблица ГДИ

- Reader находит columns по semantic headers: field, well, plast, research
  type, date, depth, coefficient `a`, RFP, LND reliability.
- Research label хранится вместе с raw string. Валидные классы: ID, ID_KVD,
  KVD; depth — отдельный атрибут глубинности.
- По текущему Береговому source исправленный classifier дает 32 ID, 867 ID_KVD,
  702 KVD, 209 EXCLUDED и 22 UNKNOWN. Предыдущий classifier давал 33, 866, 695,
  209 и 29 соответственно. Аудит без исходных строк: `GDI_KIND_AUDIT.md`.

## `Статус исследований_2026.xlsx`

- Workbook содержит рабочие листы `АР_таблица_БЛУ`, `АР_таблица_ПЛУ`,
  `АР_таблица_ХЛУ` и листы статистики. Reader выбирает лист по LU code mapping.
- В `АР_таблица_БЛУ` заголовки многострочные, данные начинаются примерно с
  строки 6. Semantic mapping: well, plast, research type, date, Delta.
- Delta бывает numeric, `-`, blank, Excel error и formula. Читаются `data_only`
  cached values и отдельно formula text; отсутствие formula cache не превращают
  в ноль. `abs(Delta)>5` дает row-level candidate.
- Решение, какая историческая строка актуальна, пока открыто. Target
  `Проблемы ГДМ` остается пустым.

## База ЛХА и суточный рапорт

- ЛХА использует лист `БД Сибнефтегаз`, field/well/plast/timestamp/Cl/VGF.
  Одинаковые metric+timestamp сводятся к максимальному valid numeric значению;
  ноль остается числом, missing и invalid имеют разную диагностику.
- Suffixless LHA source после lifecycle boundary присоединяется только при
  однозначных field/root/date/plast/lifecycle.
- Суточный рапорт: лист `Добыча телеметрия`, schema проверяет `ГСК` и `СКВ.`.
  Читатель сохраняет данные для будущей формулы среднего дебита; target `Дебит`
  заблокирован до определения работающего дня. `ГСК` в этом source не является
  canonical field label, поэтому его строки не участвуют в per-field coverage.

## Реальные файлы и synthetic tests

Production files in `data/` are git-ignored. Integration tests skip automatically
when the complete source bundle is absent. CI uses small synthetic workbooks
without production rows.
