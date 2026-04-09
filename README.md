# Офлайн RAG-платформа первой линии поддержки ЦСВ АНС

Репозиторий содержит полностью локальный стек (без интернета и облаков) для запуска чат-бота поддержки на базе документации ЦСВ АНС и внутренних нормативных документов.

## Зафиксированный стек моделей
- LLM: `qwen2.5-7b-instruct-q4_k_m.gguf`
- Vision: `Qwen3-VL-2B-Instruct` (локально в `models/vision/qwen3-vl-2b-instruct/`)
- OCR: `PaddleOCR` (локальные веса в `models/ocr/`)
- Embeddings: `BAAI/bge-m3` (локально в `models/embeddings/bge-m3/`)
- Reranker: `BAAI/bge-reranker-v2-m3` (локально в `models/reranker/bge-reranker-v2-m3/`)

## GPU-ускорение retrieval в `support-api`
- `support-api` может выполнять embeddings и reranker на GPU (`cuda`) через `sentence-transformers`.
- По умолчанию в `.env.example` включён CUDA-режим:
  - `SUPPORT_API_TORCH_DEVICE=cuda`
  - `EMBEDDING_DEVICE=cuda`
  - `RERANKER_DEVICE=cuda`
- Для принудительного CPU-режима переопределите:
  - `SUPPORT_API_TORCH_DEVICE=cpu`
  - `EMBEDDING_DEVICE=cpu`
  - `RERANKER_DEVICE=cpu`


## Мультимодальный режим (single-cutover)
- `/ask` и `/v1/chat/completions` принимают текст и изображения пользователя.
- Скриншоты проходят OCR + визуальный анализ; результат включается в prompt и возвращается полем `visual_evidence`.
- Ingest DOCX/PDF извлекает изображения, строит OCR/caption чанки и индексирует их в Qdrant наравне с текстом.

## Состав решения
- Open WebUI (чат-интерфейс)
- FastAPI (кастомный backend)
- Qdrant (векторный поиск)
- llama.cpp server (локальная LLM)
- PostgreSQL (метаданные)
- Prometheus + Grafana (метрики)
- Loki + Promtail (централизованные логи)

## Ссылки на документы-основания
- В ответе API (`/ask` и `/v1/chat/completions`) каждый элемент `sources` содержит поле `download_url`.
- По ссылке вида `/sources/{source_type}/{doc_id}/download` можно скачать исходный документ, на который ссылается ответ.

## Предварительные требования
Перед запуском убедитесь, что в текущем shell доступны Docker и Docker Compose v2:

```bash
docker --version
docker compose version
```

Если видите ошибку `docker: command not found`, сначала выполните подготовку из подробной инструкции: [`docs/deployment_wsl2.md`](docs/deployment_wsl2.md#1-предварительные-условия).

### Обязательное требование для `llm-server` (GPU)
- В `docker-compose.yml` для `llm-server` обязательно задано `gpus: all` (нельзя полагаться только на `deploy.resources...`).
- Переменные `NVIDIA_VISIBLE_DEVICES=all` и `NVIDIA_DRIVER_CAPABILITIES=compute,utility` должны оставаться включёнными.
- На старте контейнера выполняется fail-fast проверка: если `LLM_N_GPU_LAYERS > 0`, но GPU в контейнере недоступна, `llm-server` завершится с понятной ошибкой.

## Быстрый старт
```bash
cp .env.example .env
./scripts/bootstrap_offline.sh --mode offline
./scripts/preflight_check.sh --mode offline
docker compose up -d
```

## Обновление проекта и безопасный перезапуск
Рекомендуемый способ обновления — использовать единый скрипт:

```bash
./scripts/update_app.sh --mode offline
```

Скрипт выполняет шаги в безопасном порядке:
1. Проверяет, что рабочее дерево Git чистое (без `staged`/`unstaged` изменений).
2. Останавливает весь стек (`docker compose down --remove-orphans`).
3. Выполняет `git fetch --all --prune`.
4. Выполняет `git pull --ff-only` (без merge-коммитов).
5. Запускает `./scripts/preflight_check.sh --mode <offline|online>`.
6. Автоматически определяет, нужно ли пересобирать `support-api`:
   - если изменились входы образа (например `app/src`, `app/pyproject.toml`, `app/Dockerfile`, `app/wheels`, `docker-compose.yml`) — запускает `docker compose up -d --build`;
   - если входы не менялись — запускает `docker compose up -d` без пересборки.

Режимы работы:
- `--mode offline` (по умолчанию): `preflight_check.sh` проверяет, что `app/wheels` содержит полный набор wheel для прямых и транзитивных зависимостей.
- `--mode online`: пустой `app/wheels` допускается; если wheelhouse заполнен — он используется в приоритете, затем fallback на PyPI.

Примеры:
```bash
./scripts/update_app.sh --mode offline
./scripts/update_app.sh --mode online
./scripts/update_app.sh --mode online --build   # принудительная пересборка
```

Если нужен «чистый» старт без существующих данных, отдельно используйте `docker compose down -v`.

## Офлайн-сборка Python-зависимостей
Для закрытого контура без доступа к PyPI используйте локальный wheelhouse (`app/wheels`) и инструкции в [`docs/operations.md`](docs/operations.md#устойчивость-сборки-python-зависимостей-и-офлайн-режим).

Для безопасного наполнения и обновления wheelhouse используйте:
```bash
./scripts/update_wheels.sh --mode refresh
```

Для онлайн-сборки можно переопределить индекс Python-пакетов через build args:
```bash
docker compose build \
  --build-arg PIP_INDEX_URL=https://pypi.org/simple \
  --build-arg PIP_EXTRA_INDEX_URL= \
  --build-arg PIP_TRUSTED_HOST=
```

## Документация
- [Архитектура](docs/architecture.md)
- [Реестр моделей](docs/model_registry.md)
- [Развёртывание в WSL2 (подробно)](docs/deployment_wsl2.md)
- [Эксплуатация](docs/operations.md)
- [Single-cutover мультимодальный запуск](docs/multimodal_single_cutover.md)


## Автотесты
Базовый стек автотестов:
- `pytest`
- `pytest-cov`

Локальный запуск всех автотестов:
```bash
cd app
pip install -e .[dev]
pytest -q --cov=src --cov-report=term-missing
```

Перед merge в GitHub необходимо запускать **все** автотесты локально и проверять, что CI `tests` в Pull Request зелёный.
