# Открытые вопросы и ограничения источников

Подтверждённые темы `Вопросы_v2`/`Вопросы_v3` закрыты и реализованы. Ниже нет
blocker, мешающего обычному `validate`/`update`.

## Реальная структура суточного рапорта

На листе `Добыча телеметрия` в текущем production файле колонка `ГСК` не содержит
canonical field name, а у части well identities нет однозначной связи с полем.
Для 12 Береговых target rows соответствующий daily record нельзя безопасно
выбрать по field + well; `Дебит` поэтому остаётся blank с diagnostic. Если в
будущем source schema будет содержать однозначный код месторождения или заказчик
подтвердит безопасное правило assignment, reader можно расширить. До этого не
переносить rate через совпадение номера между месторождениями.

## Historical ГДМ window — closed in v0.22

Новое требование заказчика заменило временное окно365: default730 elapsed days
включительно от calculation date для любого выбранного Δ в current history/plast.
731 дней исключено; explicit пользовательские окна сохраняются. Детальный
контракт: [CUSTOMER_DECISIONS.md](CUSTOMER_DECISIONS.md).

## Иные исходные неоднозначности

Конкретные source rows, которые не проходят однозначное lifecycle/plast
сопоставление, остаются нерешёнными с diagnostics и пустыми target cells.
Агрегаты текущего production run, включая причины и влияние на coverage,
зафиксированы в [`REAL_DATA_DELTA_v0.19.md`](REAL_DATA_DELTA_v0.19.md). Это
quality issues источника, а не основание выбирать случайного кандидата.

## Production data quality: 10306 (v0.18)

В истории скважины 10306 отсутствует событие ЗБС, но в источнике ГДИ есть
исследования 10306_ЗБС. Нужно подтвердить, была ли выполнена ЗБС и с какой
даты следует считать новую историю. До ответа INITIAL остается подтвержденным
этапом, current count=0 / NO_GDI; loader сообщает
`GDI_UNCONFIRMED_LIFECYCLE_RECORDS` и не создает событие из исследований.

## v0.19 corrective state

Underscore plast mismatch Пырейного — parser defect, устранен общей grammar;
нового business decision не требует. 10306 остается нерешенным source-quality
вопросом выше. В v0.19 конфликты 10304/10404/10503 не разрешались автоматически. В v0.22
новый authoritative Summary plast contract устраняет Fund/Base plast conflicts
при подтверждённой текущей истории; произвольное lifecycle assignment запрещено.
Multi-field current state: [REAL_DATA_DELTA_v0.19.md](REAL_DATA_DELTA_v0.19.md).
