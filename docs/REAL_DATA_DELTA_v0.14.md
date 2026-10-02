# Production regression v0.14 corrective pass

Проверка повторена на production bundle из `data/` для Берегового с расчетной
датой `2026-10-02`, одинаковыми входами и default `CriteriaConfig` в точном
v0.13 baseline (`3d99cbe`) и исправленном коде. Источники и сгенерированные
калькуляторы в Git не добавлялись. Здесь приведены только агрегаты и четыре
утверждённых customer examples.

## PVLG/PNLG identity

Среди текущих eligible target identities обнаружены 2 этапа `ПВЛГ` и 0 этапов
`ПНЛГ`. В истории источника есть 8 событий `ПВЛГ`; это число включает исторические
ветви и не является числом current targets. На двух current PVLG targets v0.13
не отображал source suffix `_ПВЛГ`/`_ПНЛГ`; исправление изменило 0 target well
numbers. Полный сравнительный прогон показал 0 изменившихся полей в 78 строках
`Данные`, включая `Скважина`, пласты и все производные значения. Метрики совпали:
69 однозначных matches, 9 ambiguous, 0 без ГДИ; Debit — 57 заполненных, 12 blank,
1,355 рабочих дневных значений; ГДМ — 4 Да, 45 Нет, 20 blank.

Target display number и lifecycle history — разные сведения. Регрессионные тесты
проверяют, что до и после `ПВЛГ` display number может быть одинаковым, а stages,
launch date и история ГДИ остаются раздельными. Тесты также фиксируют прежнее
поведение `ЗБС` (suffix/ordinal), `ГС` и `МЗС`.

## Повторная сверка количества ГДИ

Полная независимая сверка Берегового: 1,832 raw GDI rows, 1,830 после exact
dedupe, 69 resolved eligible identities, 9 unresolved identities, 0
необъяснимых расхождений с калькулятором. Из 768 deduplicated valid rows текущих
lifecycle/plast 16 относятся к дате до запуска и 751 — к запуску или позже;
одна строка без даты не включается в счётчик.

| Скважина | Запуск | До запуска | После запуска | Калькулятор | Результат |
|---|---|---:|---:|---:|---|
| 12 | 01.02.2008 | 1 | 20 | 20 | PASS |
| 13 | 01.05.2002 | 0 | 21 | 21 | PASS |
| 21 | 01.03.2004 | 0 | 19 | 19 | PASS |
| 22 | 01.03.2004 | 0 | 19 | 19 | PASS; первая запись — 01.04.2004 |

Значения совпали с v0.13 customer regression; PVLG/PNLG identity fix не менял
эти четыре истории.

## Критерии и formula layer

Default criteria snapshot в JSON отчёте совпадает с предыдущим набором:
`insufficient_gdi_min_count=2`, `productivity_min_increase=0`, пороги chlorine
`2000/1000`, `downhole_depth_threshold_m=0`, `gdm_abs_delta_threshold=5`,
`gdm_fallback_max_age_days=365`, `gas_rate_working_day_min_rate=0`. Для всех значений
origin остаётся `default`; тесты config сохраняют поведение явных значений и
ошибочных значений.

Runtime diagnostic теперь описывает требование как бизнес-правило: `μi` должен
быть `0`, критерий должен быть исключён из итогового `λ`; текущие формулы пока не
обеспечивают это полностью. Formula sheets не изменялись. Отдельный этап
[`STRUCTURAL_CALCULATOR_MIGRATION.md`](STRUCTURAL_CALCULATOR_MIGRATION.md)
сохраняется.

## OOXML

Сравнение source calculator и output:

- 78 строк данных; `tblData=A6:Z84`;
- conditional formatting `A7:A84`;
- `x14ac` namespace и `mc:Ignorable` сохранены;
- stale rows отсутствуют; максимальный номер строки листа — 84;
- отличаются ровно `xl/worksheets/sheet3.xml` и `xl/tables/table2.xml`;
- множества ZIP entries совпадают; каждый нетаргетный ZIP entry byte-identical.

Листы формул и прочие части книги не менялись.
