# PROMPTS.md

## Назначение
Фиксирует принципы prompt-building в проекте и правила изменения prompt-логики.

## Где формируется prompt
- Основная логика: `app/src/rag/prompt_builder.py`.
- Оркестрация вызова LLM: `app/src/rag/orchestrator.py`.

## Текущий формат (v1)
1. Вход: вопрос пользователя + retrieved chunks + (опционально) visual evidence.
2. Требование: ответ должен опираться на retrieved context.
3. На выходе API возвращает:
   - `answer`
   - `sources`
   - `images`
   - `visual_evidence`

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
