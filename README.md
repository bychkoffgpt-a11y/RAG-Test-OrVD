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
- В `/v1/chat/completions` поддержаны image-вложения форматов `file://`, `data:image/...;base64,...` и `http(s)://...` (с материализацией в `${FILE_STORAGE_ROOT}/runtime_uploads`).

### Переключение vision-режимов (runtime/ingest)
Для обратной совместимости по умолчанию сохранён OCR-режим.

- `VISION_RUNTIME_MODE=ocr|vlm` — режим распознавания вложений пользователя в runtime (`/ask`, `/v1/chat/completions`).
- `VISION_INGEST_MODE=ocr|vlm` — режим распознавания изображений, извлечённых из DOCX/PDF в ingest.

Параметры VLM:
- `VISION_MODEL_PATH=/models/vision/qwen3-vl-2b-instruct`
- `VISION_MODEL_DEVICE=auto|cpu|cuda`
- `VISION_MODEL_DTYPE=auto|float32|float16|bfloat16`
- `VISION_MODEL_MAX_NEW_TOKENS=160`
- `VISION_MODEL_PROMPT_RUNTIME=...`
- `VISION_MODEL_PROMPT_INGEST=...`

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
- На старте контейнера больше не выполняется принудительное переключение на CPU: сервис сохраняет заданный `-ngl`, чтобы не ломать GPU-режим в окружениях, где CUDA доступна, но `/dev/nvidia*` определяется нестандартно.

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
- `--mode online`: пустой `app/wheels` допускается; если wheelhouse заполнен — он используется в приоритете, затем fallback на primary индекс (`PIP_INDEX_URL`) и mirror (`PIP_FALLBACK_INDEX_URL`).

Примеры:
```bash
./scripts/update_app.sh --mode offline
./scripts/update_app.sh --mode online
./scripts/update_app.sh --mode online --build   # принудительная пересборка
./scripts/update_app.sh --files-only            # только безопасный git fetch/pull без остановки/перезапуска контейнеров
```

Если нужен «чистый» старт без существующих данных, отдельно используйте `docker compose down -v`.

## Офлайн-сборка Python-зависимостей
Для закрытого контура без доступа к PyPI используйте локальный wheelhouse (`app/wheels`) и инструкции в [`docs/operations.md`](docs/operations.md#устойчивость-сборки-python-зависимостей-и-офлайн-режим).

Для безопасного наполнения и обновления wheelhouse используйте:
```bash
./scripts/update_wheels.sh --mode refresh
```

### Воспроизводимая offline-first сборка base-образов (`support-api` и `ingest`)
Теперь сборка разделена на 3 уровня:
1. **OS base** (APT-зависимости, собирается в online-контуре и переносится в offline);
2. **deps base** (`support-api-base` / `ingest-base`, ставит Python-зависимости из wheelhouse);
3. **runtime** (`support-api`, `ingest-a`, `ingest-b`) — быстрые пересборки кода от готового deps base.

#### Рекомендуемые переменные `.env`
```env
# support-api runtime/deps
SUPPORT_API_BASE_IMAGE_REPO=cr.yandex/<registry_id>/rag-support-api-base
SUPPORT_API_DEPS_TAG=dev

# OS base images (APT слой)
SUPPORT_API_OS_BASE_IMAGE_REPO=cr.yandex/<registry_id>/rag-support-api-os-base
INGEST_OS_BASE_IMAGE_REPO=cr.yandex/<registry_id>/rag-ingest-os-base
SUPPORT_API_OS_TAG=latest
INGEST_OS_TAG=latest

# ingest deps
INGEST_BASE_IMAGE_REPO=cr.yandex/<registry_id>/rag-ingest-base
INGEST_DEPS_TAG=dev

# yandex registry auth helper
YC_REGISTRY_ID=<registry_id>
YC_DOCKER_AUTH=auto

# pip / wheelhouse
PIP_INDEX_URL=https://pypi.org/simple
PIP_FALLBACK_INDEX_URL=https://mirror.yandex.ru/mirrors/pypi/simple
PIP_EXTRA_INDEX_URL=
PIP_TRUSTED_HOST=
PIP_MODE=auto
PIP_ONLINE_FALLBACK=1
FORCE_BUILDKIT=0

# unified CUDA torch stack
PYTORCH_CUDA_INDEX_URL=https://download.pytorch.org/whl/cu128
TORCH_VERSION=2.10.0
TORCHVISION_VERSION=0.25.0
TORCHAUDIO_VERSION=2.10.0

# wheel target
TARGET_PLATFORM=manylinux2014_x86_64
TARGET_PYTHON_VERSION=311
TARGET_IMPLEMENTATION=cp
TARGET_ABI=cp311
```

#### Полный online→offline pipeline
1. Подготовьте wheelhouse (включая CUDA torch stack):
   ```bash
   ./scripts/update_wheels.sh --mode refresh --strict
   ```
2. Соберите OS base образы (APT-слой):
   ```bash
   PUSH_IMAGE=1 OS_TAG=2026-04-21 ./scripts/build_os_base_images.sh
   ```
3. Соберите deps base для `support-api`:
   ```bash
   SUPPORT_API_OS_BASE_IMAGE="${SUPPORT_API_OS_BASE_IMAGE_REPO}:${SUPPORT_API_OS_TAG}" \
   IMAGE_REPO="${SUPPORT_API_BASE_IMAGE_REPO}" PUSH_IMAGE=1 PIP_MODE=offline ./scripts/build_support_api_base.sh
   ```
4. Соберите deps base для ingest:
   ```bash
   INGEST_OS_BASE_IMAGE="${INGEST_OS_BASE_IMAGE_REPO}:${INGEST_OS_TAG}" \
   IMAGE_REPO="${INGEST_BASE_IMAGE_REPO}" PUSH_IMAGE=1 PIP_MODE=offline ./scripts/build_ingest_base.sh
   ```
5. Сохраните в `.env` теги `SUPPORT_API_DEPS_TAG` и `INGEST_DEPS_TAG` из вывода скриптов.
6. Пересоберите runtime-образы:
   ```bash
   docker compose build --no-cache support-api ingest-a ingest-b
   ```

#### Что изменилось в офлайн-гарантиях
- `build_support_api_base.sh` и `build_ingest_base.sh` в `PIP_MODE=offline` теперь делают fail-fast, если:
  - `app/wheels` пустой;
  - отсутствует локальный prebuilt OS base image.
- `Dockerfile.support-api-base` и `Dockerfile.ingest-base` больше не выполняют `apt-get`; APT вынесен в `Dockerfile.support-api-os-base` / `Dockerfile.ingest-os-base`.
- Установка CUDA torch stack в base Dockerfile теперь следует той же policy, что и остальные pip-зависимости:
  - offline: только `/wheels`;
  - online/auto: сначала `/wheels`, затем индекс.
- `support-api` runtime собирается от `${SUPPORT_API_BASE_IMAGE_REPO}:${SUPPORT_API_DEPS_TAG}` (аналогично ingest runtime от ingest base).

### Полный поток воспроизводимой сборки ingest-base (Yandex CR)
1. Подготовьте авторизацию `yc` и docker helper (если планируется push):
   ```bash
   yc init
   yc container registry configure-docker
   ```
2. Убедитесь, что `.env` заполнен (см. блок выше).
3. Пересоберите wheelhouse под target Python/ABI:
   ```bash
   ./scripts/update_wheels.sh --mode refresh --strict
   ```
4. Соберите и опубликуйте ingest-base:
   ```bash
   INGEST_OS_BASE_IMAGE="${INGEST_OS_BASE_IMAGE_REPO}:${INGEST_OS_TAG}" \
   IMAGE_REPO="${INGEST_BASE_IMAGE_REPO}" PUSH_IMAGE=1 PIP_MODE=offline ./scripts/build_ingest_base.sh
   ```
5. Возьмите напечатанный `INGEST_DEPS_TAG=...` и сохраните в `.env`.
6. Пересоберите ingest-сервисы:
   ```bash
   docker compose build --no-cache ingest-a ingest-b
   ```

### BuildKit frontend preflight и offline fallback
- Скрипты `build_support_api_base.sh` и `build_ingest_base.sh` теперь:
  - в `PIP_MODE=offline` по умолчанию выставляют `DOCKER_BUILDKIT=0`, чтобы не требовать pull `docker/dockerfile:1.7` с Docker Hub;
  - поддерживают override через `FORCE_BUILDKIT=1`;
  - в BuildKit-режиме выполняют preflight-проверку доступности `docker/dockerfile:1.7` через `docker buildx imagetools inspect`.
- Для репозиториев `cr.yandex/*` скрипт ingest-базы конфигурирует `yc` auth только если:
  - `YC_DOCKER_AUTH=1`; или
  - `YC_DOCKER_AUTH=auto` и `PUSH_IMAGE=1`.
  Во всех остальных случаях авто-конфиг пропускается.

### Troubleshooting: `403 Forbidden` при pull `cr.yandex/<registry_id>/rag-ingest-base:*`
Если при `docker compose build ingest-a`/`ingest-b` возникает ошибка вида:
`failed to authorize ... cr.yandex ... 403 Forbidden`, это означает, что
реестр Yandex Container Registry не разрешает pull для указанного образа/тега без авторизации.

Рабочие варианты:
1. Авторизоваться в Yandex CR и повторить сборку:
   ```bash
   yc container registry configure-docker
   docker compose build --no-cache ingest-b
   ```
2. Если вы работаете полностью локально, собрать base image локально и использовать локальный repo/tag:
   ```bash
   IMAGE_REPO=local/rag-ingest-base DEPS_TAG=dev ./scripts/build_ingest_base.sh
   export INGEST_BASE_IMAGE_REPO=local/rag-ingest-base
   export INGEST_DEPS_TAG=dev
   docker compose build --no-cache ingest-b
   ```

Чтобы закрепить локальный вариант, добавьте в `.env`:
```env
INGEST_BASE_IMAGE_REPO=local/rag-ingest-base
INGEST_DEPS_TAG=dev
```

### Troubleshooting: `error getting credentials` на `docker.io/docker/dockerfile:1.7`
Если `build_ingest_base.sh`/`build_support_api_base.sh` падает на шаге:
`resolve image config for docker-image://docker.io/docker/dockerfile:1.7`
с сообщением `error getting credentials`, это ошибка credential helper или доступа к Docker Hub для BuildKit frontend.

Рекомендуемые шаги:
1. Для офлайн-сборки использовать режим по умолчанию с отключённым BuildKit:
   ```bash
   PIP_MODE=offline ./scripts/build_ingest_base.sh
   ```
   (скрипт сам выставит `DOCKER_BUILDKIT=0`, если не задан `FORCE_BUILDKIT=1`).
2. Если требуется BuildKit, проверить preflight вручную:
   ```bash
   docker buildx imagetools inspect docker/dockerfile:1.7
   ```
3. Проверить docker credential helper:
   - временно отключить проблемный helper в `~/.docker/config.json` и повторить;
   - или выполнить `docker login` для нужного реестра вручную.
4. Для Yandex CR включать авто-настройку helper только при необходимости:
   ```bash
   YC_DOCKER_AUTH=auto PUSH_IMAGE=1 ./scripts/build_ingest_base.sh
   ```

### Troubleshooting: `KeyError: 'qwen3_vl'` / `Transformers does not recognize this architecture`
Если в `ingest-a`/`ingest-b` при `VISION_*_MODE=vlm` появляется ошибка про `qwen3_vl`,
это признак несовместимой версии `transformers` внутри ingest-образа.

Проверка внутри контейнера:
```bash
docker compose run --rm ingest-b python -c "import transformers; print(transformers.__version__)"
docker compose run --rm ingest-b python -c "from transformers import AutoConfig; print(AutoConfig.from_pretrained('/models/vision/qwen3-vl-2b-instruct', trust_remote_code=True, local_files_only=True).model_type)"
```

Рекомендуемый порядок исправления:
1. Пересобрать и (опционально) опубликовать ingest-base:
   ```bash
   IMAGE_REPO="${INGEST_BASE_IMAGE_REPO}" PUSH_IMAGE=1 PIP_MODE=offline ./scripts/build_ingest_base.sh
   ```
2. Обновить `INGEST_DEPS_TAG` в `.env` на новый тег из вывода `build_ingest_base.sh`.
3. Пересобрать ingest-сервисы без кэша:
   ```bash
   docker compose build --no-cache ingest-a ingest-b
   ```
4. Прогнать preflight:
   ```bash
   ./scripts/preflight_check.sh --mode offline --check-ocr-stack
   ```

## Документация
- [Архитектура](docs/architecture.md)
- [Реестр моделей](docs/model_registry.md)
- [Развёртывание в WSL2 (подробно)](docs/deployment_wsl2.md)
- [Эксплуатация](docs/operations.md)
- [Single-cutover мультимодальный запуск](docs/multimodal_single_cutover.md)

## Регрессионная проверка OCR/Vision/Retrieval (5 кейсов)
В репозитории добавлен автоскрипт `scripts/run_vision_regression.py`, который:
- генерирует контрольные изображения и PDF с embedded-изображением в `data/`;
- запускает 5 positive/negative проверок мультимодального API;
- делает ingestion корпуса A, отдельно валидирует факт индексации `vision_regression_marker`
  (документ + число чанков) и только затем проверяет retrieval по image-derived OCR-маркеру;
- печатает единый PASS/FAIL отчёт и завершает работу с ненулевым кодом при фейле.

Быстрый запуск:
```bash
python3 scripts/run_vision_regression.py --api-url http://localhost:8000
```

Полезные флаги:
```bash
python3 scripts/run_vision_regression.py --help
python3 scripts/run_vision_regression.py --marker-token ERR-9A7K-UNIQUE
python3 scripts/run_vision_regression.py --prefer-docker-for-assets
python3 scripts/run_vision_regression.py --expected-runtime-mode ocr --expected-ingest-mode ocr
python3 scripts/run_vision_regression.py --expected-runtime-mode vlm --expected-ingest-mode vlm
python3 scripts/run_vision_regression.py --expected-runtime-mode vlm --expected-ingest-mode vlm --debug-tc4-soft
```

Примечания по режимам:
- `TC-02` зависит от `--expected-runtime-mode`:
  - `ocr`: строгая проверка по `visual_evidence[].ocr_text` (ожидается код ошибки, например `500`);
  - `vlm`: допускается пустой `ocr_text`, проверяется содержательный `summary`.
- `TC-04` зависит от `--expected-ingest-mode`:
  - `ocr`: strict retrieval маркерного документа (`vision_regression_marker`);
  - `vlm`: semantic retrieval (ослабленная проверка, без обязательного exact-token).

## Проверка корректности распознавания через VLM
Добавлен отдельный smoke-скрипт `scripts/run_vlm_recognition_checks.py`, который:
- генерирует runtime-изображения форматов `png/jpeg/bmp/tiff`;
- проверяет runtime-распознавание через `VisionService` в режиме `VLM`;
- собирает DOCX/PDF с изображениями, извлекает image assets парсерами и валидирует ingest-распознавание через `VLM`.

Запуск:
```bash
python3 scripts/run_vlm_recognition_checks.py --work-dir data/vision_vlm_checks --keep-assets
```

> Скрипт ожидает, что `./data` смонтирован в `support-api` как `/data` (штатная конфигурация `docker-compose.yml`).

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

Для уже развёрнутой production-инсталляции доступен отдельный скрипт запуска тестов в одноразовом контейнере (без перезапуска сервисов):
```bash
./scripts/run_tests_prod.sh                         # все тесты
./scripts/run_tests_prod.sh --groups unit          # только unit
./scripts/run_tests_prod.sh --groups integration   # только integration
./scripts/run_tests_prod.sh --groups unit,integration --coverage
```
