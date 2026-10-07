# Решения заказчика и границы реализации

Нормативные бизнес-правила этой версии взяты из объединённой формы `Вопросы_v2`,
последующей формы `Вопросы_v3` и последнего прямого уточнения по `Дельта ГДМ`.
Приоритет источников: последние ответы v2/v3; последнее уточнение по ГДМ;
`Описание`; текущие production sources; calculator; README. Старые PPTX/DOCX
служат только контекстом. Исторические блокеры перечислены в
[`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md); все перечисленные ниже закрыты.

## Scope, validation и output

- `validate` проверяет только входные файлы, обнаруживает canonical месторождения
  из фонда и сообщает покрытие sources. Он не зависит от output path и не меняет
  файловую систему результата.
- `update` требует явного выбранного месторождения. В target входят только
  дающие, дающие газ и остановленные в отчетном периоде; состояния записываются
  как `Дающие газ` и `Остановленные в отчетном периоде`.
- Пустой output получает имя `<calculator>_UPDATED_<field>.xlsx`; явный output
  не изменяется. Перед update проверяются расширение, совпадение с входными
  файлами и каталог результата.
- В `config.toml` допускаются только числовые критерии из schema приложения.
  `CriteriaConfig` — immutable snapshot на одну операцию; отчёт хранит значения,
  происхождение (`default`/`config`) и путь конфигурации.
- Колонки `Расходомер`, `Последний АДД`, `Не проведен АДД`, `Техническая
  возможность`, `Manual μ` остаются пустыми. `ГТМ` пока заполняется временным
  значением `Нет`.

## Даты

Сохранять raw value, исходную точность и provenance отдельно от effective date:

- DAY — исходный календарный день;
- MONTH (`MM.YYYY`) — первое число месяца;
- YEAR (`YYYY`) — 1 января.

Например, `07.2020 -> 2020-07-01`, `2015 -> 2015-01-01`. Это согласованное
правило расчётов, а не точность, присутствовавшая в исходнике. Числовая дата
разбирается с учётом number format; `7.202` при `0.0000` означает `07.2020`.
Некорректное значение остаётся diagnostic. `calculation_date` — локальная
системная дата, полученная один раз в начале операции.

## Lifecycle и identity

Новые lifecycle histories начинаются после `ЗБС`, `ПВЛГ` и `ПНЛГ`. `ПВР`, `КЛК`
и прочие ГТМ сами по себе границей не являются.

- `ПВЛГ`/`ПНЛГ` начинают новую lifecycle history, но target display/canonical
  well number наследуется от родительского stage (включая ordinal ЗБС),
  без source suffix `_ПВЛГ`/`_ПНЛГ`;
  меняются этап, дата запуска, актуальный пласт и соответствующая история ГДИ/ЛХА/ГДМ.
- Для последовательных текущих ЗБС использовать детерминированный ordinal
  (`_ЗБС`, `_ЗБС2`, `_ЗБС3`) по fund и истории. Не нумеровать произвольно
  исторические или неактуальные ветви.
- `ГС` и `МЗС` — отдельные скважины и histories; не сливать их с mother well.
- `base_well_id` служит только lineage search key. Основная identity включает
  field, physical root, lifecycle stage и актуальный plast. Начальные нули
  числовой части незначимы. Неоднозначные temporal matches остаются пустыми.

Если у текущей eligible fund-записи ещё нет ГДИ, current lifecycle определяется
по selected field, physical root, текущему нормализованному plast, истории и
границам lifecycle. При `record=None` однозначный latest stage с совместимым
plast считается текущим; сюда входят `ПВЛГ`/`ПНЛГ` и текущий ordinal `ЗБС`.
Неоднозначные stages остаются `AMBIGUOUS` с provenance. Если lifecycle и plast
определены, но валидных ГДИ в нём нет, это `NO_GDI`, а не ошибка сопоставления:
старые записи предыдущего lifecycle запрещено использовать как fallback.

Для `NO_GDI` количество равно `0`, `Недостаточно ГДИС` вычисляется обычным
порогом (`count < min_count`, default `2`), а длительности без ГДИ/ИД/КВД
отсчитываются от effective launch, когда соответствующей истории текущего
lifecycle нет. Удельное количество ГДИ остаётся blank при нулевом знаменателе;
качественные GDI-признаки без доказательств также blank. LHA, GDM и Debit можно
заполнять при отдельном однозначном assignment по их подтверждённым ключам и
временной истории; отсутствие ГДИ их не блокирует.

## Объект фонда и exact plast

В поле `Объект` фонда parenthesized `ПК9-17` и `ПК19-20` задают диапазон
primary plasts, а не совместный exact plast. Composite current plast совместим,
если все его primary constituents входят в диапазон. Exact sources ГДИ/history/
ЛХА/ГДМ сохраняют прежнюю canonicalization: `ПК19-20 -> ПК19+20`.

Current lifecycle resolution отделен от GDI match status. GDM, Debit и ЛХА
используют собственный assignment при разрешенной lifecycle identity даже при
GDI `AMBIGUOUS`; genuine unresolved lifecycle блокирует зависимые поля.
Explicit active ordinal ЗБС выбирается до общей latest-stage логики; PVLG/PNLG
внутри ветки сохраняют ее identity. Root-only row с несколькими явно работающими
совместимыми ordinal ветками остается неоднозначной.

## Пласты

Dedicated canonicalizer применяет Unicode normalization, стабилизирует пробелы и
dash variants, извлекает основные номера и убирает sublayer suffix:

- `ПК17-2-1 -> ПК17`, `ПК14-1 -> ПК14`;
- `ПК19-20 -> ПК19+20`, `ПК14+15 -> ПК14+15`;
- составной исходный список `ПК14-1, ПК15-1 -> ПК14+15`.

Порядок частей комбинации стабилен. Не использовать fuzzy matching: одиночный
`ПК14` не эквивалентен `ПК14+15`. Raw plast сохраняется в provenance.

## Классификация и количество ГДИ

После NFKC, trim, case normalization и допустимой нормализации разделителей
классифицировать только prefix, в следующем порядке: `ИД+КВД`, `ИД`, `КВД`.
Всё после prefix — пояснение. Поэтому `ИД+КВД освоение`, `ИД+КВДсм НКТ`,
`КВДстатика`, `ИД пояснение` валидны; `Освоение`, `Статика`, `Pст`, `Pпл`,
`МЗС+миниКВД` сами по себе ГДИ не являются.

Одна запись `ИД+КВД` даёт +1 к общему количеству и одновременно обновляет
последние ID и KVD. Полные дубли по well, normalized plast, date, kind и всем
прочитанным business attributes считаются одним исследованием; provenance таких
строк объединяется, выдаётся `GDI_EXACT_DUPLICATE_COLLAPSED`. Различия глубины,
`a`, `b`, ЛНД/RFP и иных business values сохраняют отдельные исследования.

`Количество ГДИ` — число дедуплицированных валидных исследований текущей
lifecycle/plast history с effective date `>= launch`. До запуска, другая history,
иной актуальный пласт, invalid label и точные повторы не входят. `Недостаточно
ГДИС`: `count < min_count -> Да`, иначе `Нет`; default `min_count=2`. Для
unresolved identity поле остаётся blank.

Customer regression на Береговом: скв. 12 имеет один valid GDI до launch и 20
после; 13 — 21 после запуска `01.05.2002`; 21 — 19 после `01.03.2004`; 22 — 19
после `01.03.2004`, начиная с `01.04.2004`. Все четыре значения сверяются с
выпускным workbook в [`REAL_DATA_DELTA_v0.13.md`](REAL_DATA_DELTA_v0.13.md).

## Производные и числовые границы

Числовые границы редактируются в GUI `Критерии…` и централизованы в typed
`CriteriaConfig`. Строгие операторы и предметная семантика не настраиваются.

- Productivity: последние два valid GDI с numeric `a` в текущей истории;
  `(current_a - previous_a) > min_increase` — Да, иначе Нет. Default `0.0`.
  Non-GDI row не участвует; missing pair — blank.
- Chlorine: `Cl_current > current_min_mg_dm3` AND
  `Cl_current - Cl_previous > delta_min_mg_dm3`. Defaults `2000` и `1000`;
  missing inputs — blank. Для дублей metric/timestamp в LHA выбирается максимум
  valid numeric value.
- Downhole: depth последнего valid GDI `> depth_threshold_m` — Да, иначе Нет;
  default `0`. Missing/invalid — blank.
- Duration without GDI: от последнего valid GDI; если его нет — от effective
  launch. Без ID — от последнего ID/ID_KVD, или от launch, если ID не было.
  Без KVD — от последнего KVD/ID_KVD, или от launch, если KVD не было.
  Результат — actual days / 365 без округления.
- Specific GDI rate: `((calculation_date - effective_launch_date).days / 365) /
  gdi_count`; при нуле source cell остаётся blank.
- Debit: лист `Добыча телеметрия`; все дневные значения месяца для скважины,
  которые numeric и строго больше `working_day_min_rate`, усредняются
  арифметически. Default `0`; нулевые, отрицательные, blank, text и Excel errors
  не входят. Нет подходящего дня — blank с diagnostic.

## Проблемы ГДМ и missing inputs

`Дельта` строки статуса ГДМ уже сравнивает давление исследования с ГДМ на дату
того же исследования. Сравнивать разные Delta между собой нельзя. Любое finite
numeric Delta, включая отрицательное и `0.0`, valid; blank, `-`, text, Excel
error, NaN/inf — invalid.

Сначала ограничить selected field/current lifecycle/current normalized plast;
затем выбрать самую свежую строку с finite numeric Delta не позже даты расчёта.
Если новые значения invalid, искать назад. Возраст **любого** выбранного значения
относительно calculation date должен быть `0 <= age_days <= fallback_max_age_days`.
Default v0.22 — **730 дней**, граница включена (731 исключено). Это elapsed-day
window, а не три календарных года: даты 2024 допустимы только внутри окна.
Сохранённое explicit значение (включая 365) не мигрируется; missing key получает 730.
Все типы исследований разрешены. `abs(delta) > threshold` — `Да`, иначе `Нет`;
default threshold 5. Missing selected value — blank. Δ разных дат не вычитаются.
Provenance показывает выбранную cell, research date, latest/fallback и возраст
от calculation date. AutoFilter/hidden rows не ограничивают reader.

## Authoritative current plast — v0.22

После определения current identity/history по field, root, suffix/ordinal и
подтверждённым dated boundaries authoritative plast — последняя валидная
Сводная ГДИ **в этой истории** до calculation cutoff. Fund object/plast constraint
не участвует в первоначальном выборе этого stage. Temporal assignment сохраняет
existing identity, separate ГС/МЗС, ordinal и unresolved-boundary checks.
Равнодатные разные canonical plasts блокируют все plast-sensitive поля.
Локальная копия существующего WellStage получает выбранный plast; она общая для
ГДИ/count, ЛХА и ГДМ. Нормализация exact, без fuzzy equivalence.

Если safe Summary candidate не найден (нет confirmed stage, нет valid current
GDI, нет dated/field/plast key), используется прежний conservative Fund/Base
контракт, включая отказ при неоднозначности. Этот путь отмечен
`SUMMARY_GDI_CURRENT_PLAST_NOT_FOUND`; произвольный пласт не назначается.
Selection/ambiguity отмечены `SUMMARY_GDI_CURRENT_PLAST_SELECTED` /
`SUMMARY_GDI_CURRENT_PLAST_AMBIGUOUS`; provenance «Текущий пласт» сохраняет
Fund hint, выбранный пласт и overridden. ГДМ группирует причины
`GDM_DIFFERENT_PLAST_REJECTED`, `GDM_DIFFERENT_HISTORY_REJECTED` по target,
а no-data/stale window и selected date доступны в прежнем report contract.

Если для качественного признака inputs недостаточно, target field остаётся blank,
а не `Нет`. По подтверждённому бизнес-правилу `μi` должен быть `0`, а criterion
должен быть исключён из итогового `λ`. В сохраненном исходном template v0.19
этот gap остается. Отдельный structural template version2 candidate реализует
μ=0 / exclusion; canonical switch ожидает native Excel acceptance. Подробности в
[`STRUCTURAL_CALCULATOR_MIGRATION.md`](STRUCTURAL_CALCULATOR_MIGRATION.md).
Loader runtime по-прежнему не изменяет формулы и остальные листы.


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
