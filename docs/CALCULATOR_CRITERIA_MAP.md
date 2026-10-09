# Criteria map — template structural v2 candidate

criterion | source in Данные | current use / weight | μ location | transformation | current λ | new use / missing | status
---|---|---|---|---|---|---|---
Запланировано или проведено ГТМ | ГТМ | Да; 0.2 | Критерии B20:119 | Да / Нет | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | active
Недостаточно ГДИС для создания модели пласт-скважина | Недостаточно ГДИС | Да; 0.14 | Критерии C20:119 | Да / Нет | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | active
Наблюдается снижение продуктивности | Снижение продуктивности | Да; 0.12 | Критерии D20:119 | Да / Нет | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | active
Рост хлора | Рост хлора | Да; 0.12 | Критерии E20:119 | Да / Нет | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | active
Проблемы с адаптацией в ГДМ | Проблемы ГДМ | Да; 0.12 | Критерии F20:119 | Да / Нет | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | active
Невыход на радиальный режим / низкая достоверность ЛНД | ЛНД | Да; 0.1 | Критерии G20:119 | Да / Нет | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | active
Продолжительность пребывания без ГДИ | Продолжительность без ГДИ | Да; 0.1 | Критерии H20:119 | Сигмоида | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | active
Не проведен АДД за скользящий год | Не проведен АДД | Да; 0.05 | Критерии I20:119 | Да / Нет | numeric weighted geometric; missing blocks | removed slot | removed
Удельное количество ГДИ от накопленного периода работы | Удельное количество ГДИ | Да; 0.05 | Критерии J20:119 | Сигмоида | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | active
Рост ВГФ | ВГФ текущий + ВГФ предыдущий | Нет; 0.08 | Критерии K20:119 | Рост показателя | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | available, disabled
Превышение предельного ВГФ | ВГФ текущий | Нет; 0.08 | Критерии L20:119 | Больше порога | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | available, disabled
Продолжительность пребывания без ИД | Продолжительность без ИД | Нет; 0.14 | Критерии M20:119 | Сигмоида | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | available, disabled
Продолжительность пребывания без КВД | Продолжительность без КВД | Нет; 0.1 | Критерии N20:119 | Сигмоида | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | available, disabled
Возможность проведения исследований | Техническая возможность | Нет; 0.05 | Критерии O20:119 | Да / Нет | numeric weighted geometric; missing blocks | removed slot | removed
Высокодебитные скважины | Дебит | Нет; 0.1 | Критерии P20:119 | ТОП % | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | available, disabled
Достаточность ГДИС с учетом стационарного оснащения | Количество ГДИ + Глубинные датчики | Нет; 0 | Критерии Q20:119 | Количество + флаг | numeric weighted geometric; missing blocks | same transform; unknown μ=0, mask=0 | available, disabled

Последний АДД | Последний АДД | unused | none | none | none | input retained; no downstream criterion | removed
Manual μ | Manual μ | unused; generic MANUAL_MU branch only | no configured slot | none | no override | input retained; excluded from active model | unused

Последний АДД has no configured calculation slots; it remains retained. Расходомер was removed in v3 without removing formulas. Не проведен АДД=row28 and Техническая возможность=row34 must have labels/fields/codes cleared and μ/helper slots disabled. v3 keeps 25 input columns; only Расходомер is physically deleted. Manual μ is unused, retained input only. Thresholds from loader are not copied into settings.
