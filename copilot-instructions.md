# copilot-instructions.md

## Про проект
Этот репозиторий — офлайн RAG-платформа (FastAPI + Qdrant + Postgres + локальные LLM/Embeddings/Reranker/Vision).
Приоритет: стабильность, воспроизводимость, совместимость с offline-развёртыванием.

## Основные правила
1. Не предлагай облачные зависимости или внешние API без явного запроса.
2. Сохраняй существующую архитектуру модулей (`api`, `rag`, `ingest`, `storage`, `vision`, `llm`).
3. Любые изменения retrieval/chunking/reranker должны сопровождаться тестами.
4. Не ломай контракт ответов `/ask` и `/v1/chat/completions` (`sources`, `images`, `visual_evidence`).
5. Новые настройки добавляй через `src/core/settings.py` и документируй.
6. Обрабатывай timeout/HTTP-ошибки внешних клиентов явно.
7. Соблюдай structured logging и не логируй чувствительные данные.
8. Избегай крупных рефакторингов без отдельной задачи.

## Scope & Constraints
- Проект работает в offline-first режиме: не предлагать облачные сервисы по умолчанию.
- Не менять зафиксированный стек моделей без явного запроса.
- Не добавлять новые зависимости без обоснования и оценки влияния на offline wheelhouse (`app/wheels`).
- Среда запуска: WSL2 + NVIDIA GeForce RTX 5070; по умолчанию отдавать приоритет GPU-вычислениям (CUDA), а CPU использовать как fallback.

## Architecture Awareness
- Учитывать раздельные контуры: `support-api`, `ingest-a`, `ingest-b`, Qdrant, PostgreSQL.
- Для retrieval учитывать два корпуса: `csv_ans_docs` и `internal_regulations`.
- Не смешивать бизнес-логику API и ingestion, сохранять текущую модульность (`app/src/api`, `app/src/ingest`, `app/src/rag`, `app/src/storage`).

## Coding Rules (Python/FastAPI)
- Типизация обязательна для публичных функций.
- Новые env-параметры описывать в `src/core/settings.py` и документации.
- Ошибки внешних интеграций обрабатывать явно (timeout/HTTP error), как в `src/main.py`.
- Логировать структурированно, не писать секреты/PII в логи.

## RAG-specific Rules
- Любые изменения в chunking/retrieval/reranking сопровождать обновлением unit-тестов (`app/tests/unit`).
- При изменении формата `sources`/`download_url` проверять совместимость `/ask` и `/v1/chat/completions`.
- При изменениях vision/OCR учитывать `visual_evidence` и деградацию без вложений.

## Testing Expectations
- Для логики: unit-тесты в `app/tests/unit`.
- Для API-контрактов: integration-тесты в `app/tests/integration`.
- Для мультимодальности: ориентироваться на `scripts/run_vision_regression.py`.

## Do/Don’t для Copilot
- **Do:** предлагать минимальные патчи, сохранять текущие нейминги/стиль.
- **Don’t:** массовый рефакторинг без запроса, переименование публичных API, удаление метрик/логов.

## Что проверять перед предложением изменений
- Затрагивает ли изменение оба корпуса (`csv_ans_docs`, `internal_regulations`)?
- Нужны ли обновления unit/integration тестов?
- Не влияет ли изменение на offline-сборку и зафиксированный стек моделей?
- Не ломает ли изменение наблюдаемость (метрики/логи)?
