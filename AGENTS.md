# AGENTS.md

## Назначение
Этот файл задаёт правила для AI-агентов (Codex/ChatGPT) при изменениях в репозитории `RAG-Test-OrVD`.

## Контекст проекта
- Тип системы: offline-first RAG-платформа поддержки (FastAPI + Qdrant + PostgreSQL + локальные модели).
- Ключевые API: `/ask`, `/v1/chat/completions`, `/ingest/a/run`, `/ingest/b/run`, `/sources/*`.
- Основная цель изменений: повышать надёжность retrieval/generation без ломки API-контрактов.

## Обязательный порядок работы
1. Прочитать `README.md`, `CODEBASE_MAP.md`, `ARCHITECTURE.md`, `API_CONTRACTS.md`.
2. При изменениях API или RAG-логики обновить документацию в этом репозитории.
3. Перед финализацией изменений выполнить:
   - `cd app && pytest -q`
   - при изменениях пайплайнов/мультимодальности: `python3 scripts/run_vision_regression.py --api-url http://localhost:8000` (если локальный стек поднят).

## Правила изменений
- Не добавлять облачные зависимости без явного запроса.
- Не менять зафиксированный модельный стек без отдельного согласования.
- Не ломать обратную совместимость ответов `/ask` и `/v1/chat/completions` (`sources`, `images`, `visual_evidence`).
- Не логировать секреты/PII.
- Новые env-параметры добавлять в `app/src/core/settings.py` и документировать.

## RAG-правила
- Изменения в chunking/retrieval/reranker сопровождаются unit-тестами (`app/tests/unit`).
- Изменения ingestion для корпусов A/B требуют проверки на обоих наборах (`csv_ans_docs`, `internal_regulations`).
- Prompt-изменения фиксировать в `PROMPTS.md`.

## Коммиты и PR
- Формат коммитов: `type(scope): summary` (например, `docs(project): add v1 context docs`).
- В PR описывать:
  - что изменено;
  - почему;
  - как проверено;
  - риски/ограничения.
