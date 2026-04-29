# PROMPTS.md

## Назначение
Фиксирует принципы prompt-building в проекте и правила изменения prompt-логики.

## Где формируется prompt
- Основная логика: `app/src/rag/prompt_builder.py`.
- Оркестрация вызова LLM: `app/src/rag/orchestrator.py`.

## Текущий формат (v6)
1. Вход: вопрос пользователя + retrieved chunks + (опционально) visual evidence.
2. Требование: ответ должен опираться на retrieved context.
3. На выходе API возвращает:
   - `answer`
   - `sources`
   - `images`
   - `visual_evidence`
4. LLM **не должна** добавлять блоки `Основание`/`Источники` и маркеры вида `[1]`, `[2]`.
   Эти блоки добавляются backend-форматтером на основе структурированного `sources`.



## Единый vision-шаблон для `/ask` и `/v1/chat/completions`
- Выделена общая функция `build_vision_prompt(question, visual_evidence)` в `app/src/rag/prompt_builder.py`.
- Одинаковый prompt-body для vision-ветки строится в orchestrator и используется обоими endpoint через общий вызов `build_prompt(...)`.
- Системные сообщения из OpenAI-совместимого payload не подменяют этот шаблон: в `/v1/chat/completions` для RAG берётся только последнее `user`-сообщение (текст + image attachments).
- Снапшот-проверка паритета добавлена в `app/tests/integration/test_vision_prompt_snapshot_parity.py`.
## Guardrails
- Не выдумывать факты, отсутствующие в retrieved context.
- При недостатке данных явно сообщать о нехватке контекста.
- Сохранять ссылочность ответа через `sources`.

## Политика изменений prompt'ов
При любом изменении prompt-builder:
1. Обновить unit-тесты (`app/tests/unit/test_prompt_builder.py` и смежные).
2. Проверить, что формат ответа не ломает контракт API.
3. Задокументировать изменение здесь в `Prompt change log`.

## Prompt change log
- `v1` (2026-04-16): документирован текущий подход prompt-building для `RAG-Test-OrVD`.
- `v2` (2026-04-23): запретили генерацию ссылочных блоков внутри LLM-ответа; "Основание" и ссылки формируются детерминированно на backend из `sources`.

- `v3` (2026-04-29): ужесточен runtime VLM system prompt: модель обязана отвечать строго JSON по единой схеме для последующей валидации/repair.
- `v4` (2026-04-29): добавлена task-aware vision-инструкция (`text|sign|chart`) с отдельными шаблонами и ограничением top-k chart points для снижения latency/галлюцинаций.
- `v5` (2026-04-29): runtime VLM переведён на строгую схему `visible_facts[]/uncertain_facts[]/not_visible[]` + `confidence`, добавлена валидация на логические противоречия.

## Runtime VLM JSON-формат (v5)
Обязательная схема:
```json
{
  "visible_facts": ["..."],
  "uncertain_facts": ["..."],
  "not_visible": ["..."],
  "confidence": 0.0
}
```

Правила:
- Один и тот же факт **нельзя** указывать одновременно в `visible_facts`, `uncertain_facts` и/или `not_visible`.
- Если `confidence >= 0.75`, `not_visible` должен быть пустым.
- Без свободного текста вне JSON.

Примеры:

### text
```json
{
  "visible_facts": ["На экране ошибка HTTP 500", "В логе есть строка Internal Server Error"],
  "uncertain_facts": ["Кнопка Retry может быть неактивна"],
  "not_visible": [],
  "confidence": 0.91
}
```

### sign
```json
{
  "visible_facts": ["На знаке написано 'Доступ запрещен'"],
  "uncertain_facts": ["Нижняя строка может содержать код подразделения"],
  "not_visible": ["Мелкий текст в правом нижнем углу нечитаем"],
  "confidence": 0.62
}
```

### chart
```json
{
  "visible_facts": ["Линия Q2 выше Q1", "Подпись оси X: Jan-Feb-Mar"],
  "uncertain_facts": ["Точное значение в точке Mar около 120"],
  "not_visible": ["Легенда частично обрезана"],
  "confidence": 0.68
}
```

- `v6` (2026-04-29): выделен общий `build_vision_prompt(...)`; синхронизирован prompt-body vision-ветки между `/ask` и `/v1/chat/completions` snapshot-тестом паритета.
