# CODEBASE_MAP.md

## Карта репозитория

### Корень проекта
- `README.md` — быстрый старт, стек, эксплуатационные сценарии.
- `docker-compose.yml` — состав контейнеров и связи сервисов.
- `scripts/` — скрипты bootstrap/update/reindex/backup/restore/preflight/regression.
- `docs/` — предметная документация (архитектура, эксплуатация, развёртывание, модельный реестр).
- `infra/` — конфиги observability и инфраструктуры (Grafana/Loki/Prometheus/Qdrant/Postgres).
- `models/` — локальные артефакты моделей (в репозитории placeholder).
- `app/` — основной Python-сервис и тесты.

### `app/src/` (основной код)
- `main.py` — FastAPI-приложение, middleware, `/health`, `/metrics`, OpenAI-compatible endpoint.
- `api/`
  - `ask.py` — endpoint `/ask`;
  - `ingest_a.py`, `ingest_b.py` — запуск ingest pipeline A/B;
  - `sources.py` — проверка/скачивание исходных документов;
  - `schemas.py` — pydantic-модели API.
- `rag/`
  - `orchestrator.py` — основной orchestration retrieval + generation;
  - `retriever.py` — поиск и объединение кандидатов;
  - `prompt_builder.py` — сборка prompt;
  - `answer_formatter.py` — постобработка ответа и источников.
- `ingest/`
  - `pipeline_a.py`, `pipeline_b.py` — ingestion корпусов A/B;
  - `chunking.py`, `pipeline_common.py`, `dedup_hash.py` — общая логика.
  - `parsers/` — парсеры PDF/DOCX/OCR/doc conversion.
- `storage/` — интеграция с PostgreSQL/Qdrant.
- `embeddings/`, `reranker/`, `llm/`, `vision/` — клиенты/сервисы модельных компонентов.
- `core/` — settings, logging, request context.
- `telemetry/metrics.py` — метрики Prometheus.

### `app/tests/`
- `unit/` — быстрые изолированные тесты ключевой логики.
- `integration/` — тесты API/интеграций (включая OpenAI-compatible сценарии).

## Где править по задачам
- Изменить retrieval-качество: `app/src/rag/retriever.py`, `app/src/reranker/client.py`, возможно `app/src/embeddings/client.py`.
- Изменить формат/содержимое ответа: `app/src/rag/answer_formatter.py`, `app/src/api/schemas.py`, `app/src/main.py`.
- Изменить ingest по корпусам: `app/src/ingest/pipeline_a.py`, `pipeline_b.py`, `chunking.py`, `parsers/*`.
- Изменить API-контракт: `app/src/api/*` + `API_CONTRACTS.md` + тесты integration.
- Изменить env/конфиг: `app/src/core/settings.py` + docs.

## Основные команды
- Поднять стек: `docker compose up -d`
- Логи API: `docker compose logs -f support-api`
- Локальные тесты: `cd app && pip install -e .[dev] && pytest -q --cov=src --cov-report=term-missing`
- Preflight: `./scripts/preflight_check.sh --mode offline`
