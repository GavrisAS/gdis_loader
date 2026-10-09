# Structural migration шаблона — baseline loader v0.19

Эта заметка фиксирует конкретный gap, найденный read-only анализом исходного
`GDIS_Rating_Calculator_FIXED.xlsx`. Исторический baseline: в v0.13 формулы не менялись.
Принятый loader baseline v0.19 сохраняет этот formula layer без изменений.

## Требуемый downstream смысл

Когда качественный target input неизвестен из-за отсутствующих/невалидных
source values, ячейка листа `Данные` остаётся blank. Для будущего расчёта это
означает `μ=0`, при этом criterion исключается из final `λ` и не обнуляет
остальные критерии.

## Что делают текущие formula sheets

В исходном template:

1. Активные правила перечислены в `Настройки!21:29`; среди них есть
   `Не проведен АДД за скользящий год`, source field которого — `Не проведен АДД`.
   Этот target column в текущем pre-migration состоянии остаётся blank до отдельной миграции.
2. Формулы листа `Критерии` (например `Критерии!C26`) для missing source field
   возвращают текст `Недостаточно данных` (либо `Поле не найдено`).
3. `Расчет!E10` считает numeric criteria, `H10` суммирует веса только numeric
   criteria, а `J10` выдаёт blank, если `Критерии!B26:AE26` содержит
   `Недостаточно данных`, `Поле не найдено`, `Некорректные настройки` или если
   суммарный вес `H10=0`.

Следовательно, при включённом правиле с пустым `Не проведен АДД` текущий
formula flow сообщает «недостаточно данных» и оставляет `λ` пустым. Это не
равнозначно требуемому «пропустить только этот criterion и рассчитать λ по
оставшимся numeric μ».

## Историческое pre-migration решение (loader v0.19)

Loader записывает agreed blank/unknown в `Данные` и полный diagnostic provenance.
Formula sheets, weights, settings и визуальное оформление не меняются. Поля
`Расходомер`, АДД, `Техническая возможность` и `Manual μ` остаются пустыми.

Исправление формул требует отдельного согласованного structural migration с
формальным правилом обновления диапазонов, тестами формул и отдельным OOXML
review. Нельзя подменять исключение критерия multiplier `μ=0`, если это меняет
общий результат λ. До такой миграции loader report должен сообщать о разнице
между target-data semantics и formula-layer behavior.

## Нулевое количество ГДИ и sigmoid

При `gdi_count == 0` `Удельное количество ГДИ` в `Данные` остаётся blank. Для
дальнейшей методики заказчик подтвердил `μi=0`, причём такой criterion/well не
должен входить в sigmoid. Нельзя записывать искусственный numeric zero в
source cell: это может включить well в sigmoid, а multiplier zero может
обнулить общий λ вместо пропуска только этого критерия.

В будущей миграции проверить и обновить sigmoid participation, поведение
`Расчет!J`, capacity ranges `Расчет`/`Рейтинг` и любые связанные formula refs.
В историческом v0.19 scope все эти столбцы сохранялись. В текущем v3 удалён
только Расходомер; АДД и Техническая возможность сохранены.

## Current corrective baseline v0.19

Перед structural migration исправлена underscore ПК grammar и добавлена
strict generated-calculator hash revalidation. Полные production updates
проверяются для Берегового, Пырейного и Хадырьяхинского. Эта итерация меняет
только target data; `Расчет`, `Рейтинг`, `Настройки`, μ/λ formulas, weights и
calculation settings сохраняются byte-identical. Описанная выше migration
реализована отдельной offline операцией, runtime ее не вызывает.

## Offline structural template v2

Отдельный candidate реализован в `scripts/migrate_calculator_template.py`; обычный
loader его не вызывает. Исходник и rollback сохранены побайтово.
[Pre-audit](CALCULATOR_STRUCTURAL_AUDIT_PRE.md),
[criteria map](CALCULATOR_CRITERIA_MAP.md),
[math/formulas](CALCULATOR_FORMULA_MAP.md),
[OOXML diff](CALCULATOR_STRUCTURAL_DIFF.md),
[acceptance gates](CALCULATOR_STRUCTURAL_ACCEPTANCE.md).

Migration implemented offline; final automated checks are recorded in acceptance.
Template version 2 has native Excel PASS confirmed 2026-10-07. Durable tracked
assets are under `templates/calculator/`; rollback does not require code rollback.
Runtime reads capabilities and writes only Данные/tblData.

## Structural v3 / loader v0.23

v2 remains immutable and accepted. v3 deletes only the unused Расходомер data
column; all other retired inputs and the v2 formula layer are preserved.
Migration: `scripts/migrate_calculator_v3.py`; exact five-part OOXML gate and
cell-by-cell shift preservation: `tests/test_template_v3.py`.
v3 is CANDIDATE, canonical=false until new native Excel acceptance.
Current status and checklist: CALCULATOR_NATIVE_EXCEL_SMOKE.md.
