# gdis_loader

Загрузчик исходных данных в лист `Данные` калькулятора рейтингования скважин ГДИС.

## Источник бизнес-правил

Приоритет имеют последние ответы заказчика в `Вопросы_v2` и `Вопросы_v3`, затем
последнее уточнение по `Дельта ГДМ`, `Описание.txt` и текущие production sources.
Подтверждённые решения приведены в
[`docs/CUSTOMER_DECISIONS.md`](docs/CUSTOMER_DECISIONS.md); закрытые blockers не
используются как причина оставлять поддержанные поля пустыми.

## Текущий статус

`validate` находит canonical месторождения в актуальном фонде и показывает source
coverage. После проверки оператор явно выбирает ровно одно поле для `update`.
Загрузка отбирает для выбранного поля только дающие/дающие газ и остановленные в
отчетном периоде. Loader читает history, статус исследований и суточный рапорт,
различает physical root и lifecycle identity, сохраняет исходную precision и
согласованную effective date, и меняет только `Данные`/`tblData`.

## Среда

- разработка: Linux;
- целевая ОС: Windows 10/11 x64;
- Python: 3.14;
- зависимости и окружение: uv;
- Excel: openpyxl, без Excel COM;
- GUI: PySide6-Essentials (`QtCore`/`QtWidgets`);
- упаковка: PyInstaller `onedir`.

## Быстрый старт разработки

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Для повседневной разработки те же команды доступны через `make`:

```bash
make sync
make check
make run
make version
```

`make version` только показывает следующую двухкомпонентную версию `vMAJOR.MINOR`
по релизным тегам и не изменяет Git.

Запуск GUI:

```bash
uv run gdis-loader
```

CLI использует тот же application service, что и GUI. Примеры ниже используют
structural v2 candidate для testing; native Excel acceptance ещё PENDING:

```bash
uv run gdis-loader-cli validate \
  --calculator templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx \
  --fund "data/Фонд 2026 на 01.08.2026.xlsx" \
  --gdi "data/Сводная таблица ГДИ.xlsx" \
  --lha "data/База ЛХА_Итог!.xlsm" \
  --daily-report "data/07.2026 Cуточный рапорт БГП_полный.xlsm" \
  --well-history "data/База по скважинам.xlsx" \
  --research-status "data/Статус исследований_2026.xlsx"

uv run gdis-loader-cli update \
  --calculator templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx \
  --fund "data/Фонд 2026 на 01.08.2026.xlsx" \
  --gdi "data/Сводная таблица ГДИ.xlsx" \
  --lha "data/База ЛХА_Итог!.xlsm" \
  --daily-report "data/07.2026 Cуточный рапорт БГП_полный.xlsm" \
  --well-history "data/База по скважинам.xlsx" \
  --research-status "data/Статус исследований_2026.xlsx" \
  --field Береговое
```

`validate` выводит найденные месторождения без выбора target field. CLI `update`
обязательно получает `--field` (alias `--target-field`). Если `--output` не
задан, результат создаётся рядом с калькулятором как
`<calculator>_UPDATED_<Месторождение>.xlsx`.

`update` никогда не перезаписывает исходный калькулятор. Рядом с результатом
создаются `*.load-report.json` и текстовый `gdis_loader.log`. Последние пути
GUI сохраняет атомарно в `config.toml`; в PyInstaller-сборке этот файл лежит
рядом с `.exe`, в режиме разработки — в корне репозитория.

`validate` только читает и проверяет источники: `Записано строк` остаётся равным
нулю, Excel-файл результата не создаётся, а при ERROR diagnostics CLI завершает
работу с ненулевым кодом и GUI показывает ошибку. `update` записывает результат
только после успешной валидации и проверки целевой книги.

Поля `Данные` заполняются по решениям v2/v3: prefix-классификация и счётчик
валидных ГДИ, productivity, chlorine, depth, продолжительности, LHA,
`Проблемы ГДМ` и средний `Дебит`. Числовые границы находятся в `config.toml`;
GUI предоставляет модальное окно `Критерии…`. Для качественных признаков без
достаточных исходных данных target cell остаётся пустой. `ГТМ = Нет` остаётся
временным решением. Structural v2 подготовлен как отдельный candidate. Runtime расширяет только
`Данные`/`tblData`; предупреждение использует фактическую емкость template.

Управляемые критерии и defaults перечислены в
[`config.example.toml`](config.example.toml). Если файл не содержит секций
`[criteria...]`, применяются defaults; ошибочные явные значения дают validation
error. Изменение criteria не требует повторно проверять источники, а применяется
при следующем update.

Записи колонки J фонда (`в освоении / ожидании освоения`) не входят в фонд
рейтингования по исходному README, где указан действующий + бездействующий фонд.
`FUND_CATEGORY_J_IGNORED` сохраняется для аудита как INFO, а не WARNING.

Значение `153 162` в текущем фонде разбирается как два номера только при
известном контрольном количестве 2; loader сообщает об этом INFO
`FUND_MISSING_SEPARATOR_NORMALIZED` с provenance исходной ячейки. Произвольные
numeric-whitespace-ячейки без такого подтверждения не расщепляются, а при
несовпадении контрольного количества остаются диагностикой
`FUND_COUNT_MISMATCH`. Начальный ноль в числовом номере незначащий (`012 -> 12`).
Suffix в source сохраняется для разрешения lifecycle. `ЗБС` сохраняет target suffix;
`ГС` и `МЗС` остаются отдельными скважинами. После `ПВЛГ`/`ПНЛГ` target number
равен физическому корню без source suffix, при этом новая lifecycle history остаётся отдельной.

Материнская скважина, `ЗБС`, `ПВЛГ`, `ПНЛГ`, `ГС` и `МЗС` не схлопываются в одну
lifecycle history. `physical_root` используется для поиска lineage; соответствие
без суффикса допускается лишь при подтверждении полем, пластом, датой и базой истории.

Проверка коллизий `Скважина + Пласт` остается общей для подготовленных target
rows. Поскольку один update содержит только выбранное месторождение,
межместорожденийные совпадения не образуют конфликт в текущем target scope;
текущий regression не дает `TARGET_IDENTITY_COLLISION` warnings.

Диагностика использует три уровня: `ERROR` блокирует безопасное чтение или
запись, `WARNING` относится к проблеме, влияющей на текущий результат, а
ожидаемые Excel placeholders (`#DIV/0!`, `#REF!`, пустое значение, `-`) и
исторические проблемы источников попадают только в компактные `INFO`-сводки.
Каждый warning/error, связанный с исходной ячейкой, хранит structured
provenance (`file`, `sheet`, `cell`). В JSON это поле `locations`, а в обычном
логе оно выводится как `file::sheet::cell`; для ошибок структуры книги sheet/cell
могут быть `null`.

В JSON-отчете `warnings` содержит только тексты диагностик уровня `WARNING`, по
одному элементу на issue. Поле `without_lha` означает отсутствие выбранных
итоговых значений Cl/ВГФ и не доказывает физическое отсутствие записей ЛХА:
например, оно может включать строку с конфликтом одинакового timestamp.

При превышении емкости template (old: 100, v2: 1000) summary и GUI показывают
предупреждение. Неизвестная емкость сообщается явно.

`validate` не проверяет и не создаёт output path. Output extension, совпадение с
input и каталог результата проверяются непосредственно перед update.

Внизу GUI штатная status bar постоянно показывает только текущую версию
(`Версия MAJOR.MINOR`). Под кнопками действий на отдельной строке расположен
растягивающийся по ширине progress bar: каждое новое `validate`/`update` начинается
с 0, проходит детерминированные этапы
pipeline и достигает 100 только при успехе; при ошибке значение остаётся на
последней завершённой контрольной точке. Если подготовка запуска не удалась,
progress остается 0, а при ошибке уже запущенного worker значение не переводится
в 100.

## Получение Windows-сборки

Локальный Windows-ПК для сборки EXE не требуется. Каждый обычный push в `main`
запускает GitHub Actions: сначала вычисляется candidate release, затем на Windows
проходят `uv sync --locked`, проверки, PyInstaller `onedir`, frozen smoke-test и
публикация релиза:

```text
push в main -> Windows CI -> tests -> PyInstaller onedir -> smoke-test
           -> следующий MINOR -> GitHub Release
```

Workflow использует только теги и релизы формата `vMAJOR.MINOR`: `MAJOR`
сохраняется (или меняется вручную в проекте), а `MINOR` увеличивается ровно на
один. `PATCH` не используется, commit с bump версии не создаётся. Тег всегда
указывает на commit, запустивший workflow. `workflow_dispatch` на любой ветке
выполняет только тестовую сборку без повышения версии, tag и release.

Source/dev fallback — `0.1`. Для release build workflow временно генерирует
`_build_version.py`, передаёт в EXE version без `v` и проверяет её командой
`GDIS_DataLoader.exe --smoke-test --expected-version MAJOR.MINOR`. Поэтому runtime,
GUI и JSON report используют одну и ту же injected release version.

Для ручной проверки сборки откройте GitHub → **Actions** → **Build Windows** →
**Run workflow**. Ручная сборка использует dev/build version `0.1`, не создает
tag или GitHub Release, а standalone ZIP доступен только как Actions artifact
`GDIS_DataLoader-v0.1-windows-x64`. Новый release создается только после
успешного push в `main`.

Перед архивированием workflow запускает `GDIS_DataLoader.exe --smoke-test`.
Smoke-test импортирует PySide6-Essentials, openpyxl, service и writer без
открытия окна.

## Архив для внешнего аудита

После проверок создайте переносимый архив текущего рабочего состояния:

```bash
make check
make audit
```

Для audit конкретного update используйте runtime report: он содержит manifest
фактически выбранных SourcePaths и immutable criteria snapshot:

```bash
GDIS_AUDIT_RUNTIME_REPORT="reports/result.load-report.json" make audit
```

В bundle копируется только privacy-safe manifest, а не сам runtime report.
Без этой переменной manifest берет выбранные inputs/criteria из пользовательского
config; не подставляет canonical filenames вместо отсутствующих selections.
Frozen manifest берет commit/version из встроенного build module и не требует git.

`make audit` создаёт `audit/gdis_loader_audit_*.tar.xz`, включая незакоммиченные
исходники и git metadata. Реальные файлы `data/`, локальный `config.toml`,
генерированные книги, логи, caches, build и dist намеренно исключаются.

## Исходные данные

Реальные файлы помещаются в `data/`. Каталог исключен из Git. Список ожидаемых файлов см. в `data/README.md`.

## Документация

- `AGENTS.md` — обязательные правила для Codex/агентов;
- `docs/ARCHITECTURE.md` — архитектурные решения;
- `docs/SOURCE_NOTES.md` — подтвержденная структура предоставленных файлов;
- `docs/DATA_MAPPING.md` — состояние маппинга полей листа `Данные`;
- `docs/OPEN_QUESTIONS.md` — новые ограничения источников и вопросы вне текущих blockers;
- `docs/CUSTOMER_DECISIONS.md` — текущие нормативные решения заказчика;
- `docs/GDI_KIND_AUDIT.md` — агрегированный аудит классификации ГДИ без production-строк;
- `docs/REAL_DATA_DELTA_v0.11.md` — агрегированный baseline/delta и OOXML audit;
- `docs/REAL_DATA_DELTA_v0.13.md` — полная агрегированная сверка v0.13;
- `docs/STRUCTURAL_CALCULATOR_MIGRATION.md` — точный gap между blank source data и текущими формулами λ;
- `prompts/001_initial_implementation.md` — первый подробный промпт для Codex.


## Corrective pass v0.17

Общий well-id parser поддерживает `112збс`, `10404збс2`, `54ГС` и separator
variants. Bare ЗБС в конце строки задает ordinal 1; аннотированный ЗБС
(`10201збс_МГРП`) имеет unknown ordinal и разрешается по timeline/plast/date.
GS/MZS не сливаются с root; PVLG/PNLG сохраняют parent identity.
Production delta: [REAL_DATA_DELTA_v0.17](docs/REAL_DATA_DELTA_v0.17.md).
Audit provenance: [AUDIT_PROVENANCE](docs/AUDIT_PROVENANCE.md).

## Corrective pass v0.19

Общий exact-plast parser поддерживает underscore: `ПК_1 → ПК1`,
`ПК20_2 → ПК20`, `ПК20_0_1 → ПК20`, `ПК19_1+2 → ПК19`.
Underscore обрабатывается внутри ПК grammar, well-id suffix не меняется.
Dash composite `ПК19-20 → ПК19+20` и fund group `ПК9-17` сохраняют
раздельную семантику. Real integration выполняет validate/discovery и полный
update всех трех месторождений при наличии локального production bundle.
Strict runtime audit повторно проверяет все 7 sources и generated calculator.
Сверка: [REAL_DATA_DELTA_v0.19](docs/REAL_DATA_DELTA_v0.19.md).
Structural μ/λ migration реализована offline; native Excel acceptance ожидается.


## Structural template v2 candidate

Tracked assets (вариант A):
- `templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx`;
- `templates/calculator/archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx`.

Exact hashes и размеры: [metadata](docs/CALCULATOR_TEMPLATE_VERSION.toml).
Runtime изменяет только `Данные` и `tblData`. Capacity определяется read-only по
расчетной и рейтинговой таблицам. Template v2: 1000, rollback: 100.
Missing policy фиксирована; retired settings скрыты и перечислены как unused.
Manual μ остается резервом без override.

Статус: **AUTOMATED PASS / NATIVE EXCEL PENDING** после проверок этого pass.
До native gate template остается candidate. Инструкции оператора и rollback:
[Native smoke](docs/CALCULATOR_NATIVE_EXCEL_SMOKE.md).

Восстановление после clean clone: templates уже находятся в Git. Проверить
`sha256sum templates/calculator/*.xlsx templates/calculator/archive/*.xlsx`.
Для rollback выбрать архивный workbook в том же loader; исходник не менять.
Rebuild candidate в новый путь:

```bash
uv run python scripts/migrate_calculator_template.py templates/calculator/archive/GDIS_Rating_Calculator_v0.19_pre_structural.xlsx /tmp/structural-v2.xlsx
uv run python scripts/verify_calculator_template.py templates/calculator/GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx data artifacts/calculator/final-three-fields
```

Windows delivery (release v0.21): отдельные release assets рядом с
`GDIS_DataLoader-v0.21-windows-x64.zip`: `GDIS_Rating_Calculator_STRUCTURAL_v2.xlsx`,
`GDIS_Rating_Calculator_v0.19_pre_structural.xlsx`, `SHA256SUMS.txt`,
`CALCULATOR_TEMPLATE_VERSION.toml`. V2 остаётся candidate/testing до native PASS.
Checksum paths соответствуют repository layout; для downloaded assets сравнить
hash по имени файла или разместить их по указанным путям.
