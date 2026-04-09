# Офлайн RAG-платформа первой линии поддержки ЦСВ АНС

Репозиторий содержит полностью локальный стек (без интернета и облаков) для запуска чат-бота поддержки на базе документации ЦСВ АНС и внутренних нормативных документов.

## Зафиксированный стек моделей
- LLM: `qwen2.5-7b-instruct-q4_k_m.gguf`
- Embeddings: `BAAI/bge-m3` (локально в `models/embeddings/bge-m3/`)
- Reranker: `BAAI/bge-reranker-v2-m3` (локально в `models/reranker/bge-reranker-v2-m3/`; артефакт проверяется preflight, но в текущем retrieval-пайплайне не задействован)

## Состав решения
- Open WebUI (чат-интерфейс)
- FastAPI (кастомный backend)
- Qdrant (векторный поиск)
- llama.cpp server (локальная LLM)
- PostgreSQL (метаданные)
- Prometheus + Grafana (метрики)
- Loki + Promtail (централизованные логи)

## Предварительные требования
Перед запуском убедитесь, что в текущем shell доступны Docker и Docker Compose v2:

```bash
docker --version
docker compose version
```

Если видите ошибку `docker: command not found`, сначала выполните подготовку из подробной инструкции: [`docs/deployment_wsl2.md`](docs/deployment_wsl2.md#1-предварительные-условия).

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
6. Поднимает приложение `docker compose up -d --build`.

Режимы работы:
- `--mode offline` (по умолчанию): `preflight_check.sh` проверяет, что `app/wheels` содержит хотя бы один `*.whl`.
- `--mode online`: пустой `app/wheels` допускается, зависимости будут устанавливаться из PyPI во время сборки.

Примеры:
```bash
./scripts/update_app.sh --mode offline
./scripts/update_app.sh --mode online
```

Если нужен «чистый» старт без существующих данных, отдельно используйте `docker compose down -v`.

## Офлайн-сборка Python-зависимостей
Для закрытого контура без доступа к PyPI используйте локальный wheelhouse (`app/wheels`) и инструкции в [`docs/operations.md`](docs/operations.md#устойчивость-сборки-python-зависимостей-и-офлайн-режим).

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
