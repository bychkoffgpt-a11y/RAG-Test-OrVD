# Single-cutover: запуск мультимодального контура (текст + скриншоты + изображения в документах)

Документ описывает **полный** список действий, которые нужно выполнить, чтобы новый мультимодальный контур заработал сразу целиком, без промежуточных режимов.

## 1) Что должно заработать после внедрения
- `/ask` и `/v1/chat/completions` принимают текст + скриншоты пользователя.
- Скриншоты анализируются через OCR и возвращаются как `visual_evidence`.
- DOCX/PDF ingestion извлекает изображения из документов, делает OCR/caption текст и индексирует это в Qdrant как image-derived чанки.
- Логирование этапов vision-пайплайна идёт в существующий стек JSON logs + Promtail + Loki + Grafana.

## 2) Требования к окружению
- GPU: NVIDIA (в вашем случае RTX 5070 12GB)
- Docker + Docker Compose v2
- WSL2 + Ubuntu
- Для WSL2/CUDA: установлен Windows NVIDIA Driver + CUDA support для WSL2

## 3) Какие модели нужно скачать

### 3.1 Vision-модель
- Модель: `Qwen/Qwen3-VL-2B-Instruct`
- Локальный путь: `models/vision/qwen3-vl-2b-instruct/`

### 3.2 OCR-модели
- Движок: PaddleOCR
- Локальные пути:
  - `models/ocr/det/`
  - `models/ocr/rec/`
  - `models/ocr/cls/`

### 3.3 RAG-модели (уже используемые в проекте)
- Embeddings: `models/embeddings/bge-m3/`
- Reranker: `models/reranker/bge-reranker-v2-m3/`
- LLM (llama.cpp): локальный GGUF-файл по текущим настройкам проекта

## 4) Как скачать модели (онлайн-машина)

> Ниже примерный сценарий. В закрытом контуре можно скопировать каталоги с артефактами напрямую.

```bash
# Vision
huggingface-cli download Qwen/Qwen3-VL-2B-Instruct \
  --local-dir ./models/vision/qwen3-vl-2b-instruct

# Embeddings
huggingface-cli download BAAI/bge-m3 \
  --local-dir ./models/embeddings/bge-m3

# Reranker
huggingface-cli download BAAI/bge-reranker-v2-m3 \
  --local-dir ./models/reranker/bge-reranker-v2-m3
```

Для PaddleOCR скачайте offline-модели det/rec/cls и разложите в `models/ocr/{det,rec,cls}`.

> Важно: `scripts/preflight_check.sh` (функция `require_ocr_model_tree`, `components=(det rec cls)`) ожидает, что `inference.pdmodel` и `inference.pdiparams` лежат **непосредственно** в `det/`, `rec/`, `cls/`, без вложенных `*_infer/` каталогов.

Пример раскладки **до / после**:

```text
# До (НЕПРАВИЛЬНО)
models/ocr/
  det/ch_PP-OCRv4_det_infer/inference.pdmodel
  det/ch_PP-OCRv4_det_infer/inference.pdiparams
  rec/ch_PP-OCRv4_rec_infer/inference.pdmodel
  rec/ch_PP-OCRv4_rec_infer/inference.pdiparams
  cls/ch_ppocr_mobile_v2.0_cls_infer/inference.pdmodel
  cls/ch_ppocr_mobile_v2.0_cls_infer/inference.pdiparams

# После (ПРАВИЛЬНО)
models/ocr/
  det/inference.pdmodel
  det/inference.pdiparams
  rec/inference.pdmodel
  rec/inference.pdiparams
  cls/inference.pdmodel
  cls/inference.pdiparams
```

## 5) Куда положить файлы в проекте

Итоговая структура (минимум):

```text
models/
  vision/
    qwen3-vl-2b-instruct/
  ocr/
    det/
    rec/
    cls/
  embeddings/
    bge-m3/
  reranker/
    bge-reranker-v2-m3/
```

## 6) Какие переменные окружения задать

Добавьте в `.env`:

```bash
# Existing RAG settings
EMBEDDING_MODEL_PATH=/models/embeddings/bge-m3
RERANKER_MODEL_PATH=/models/reranker/bge-reranker-v2-m3
EMBEDDING_DEVICE=cuda
RERANKER_DEVICE=cuda

# New multimodal settings
VISION_ENABLED=true
VISION_INGEST_ENABLED=true
VISION_MODEL_PATH=/models/vision/qwen3-vl-2b-instruct
VISION_OCR_MODEL_ROOT=/models/ocr
VISION_OCR_LANG=ru
VISION_OCR_DEVICE=auto
VISION_OCR_USE_ANGLE_CLS=true
VISION_OCR_SHOW_LOG=false
```

## 7) Что проверить перед запуском
1. Все model-директории существуют и смонтированы в контейнеры.
2. Внутри контейнера доступны пути `/models/...`.
3. В контейнере есть доступ к GPU (`nvidia-smi` внутри GPU-сервисов).
4. В `data/inbox/...` лежат документы для индексации.

## 8) Запуск single-cutover

```bash
./scripts/preflight_check.sh --mode offline
docker compose up -d --build
```

После старта:

```bash
# Индексация документов (с image extraction + OCR)
docker compose run --rm ingest-a
docker compose run --rm ingest-b
```

## 9) Smoke checks

### 9.1 Проверка API
```bash
curl -s http://localhost:8000/health
```

### 9.2 Проверка OpenAI-compatible multimodal
Отправьте `messages` с `type=text` + `type=image_url` (`file:///...`) и убедитесь, что в ответе есть:
- `choices[].message.content`
- `sources`
- `images`
- `visual_evidence`

### 9.3 Проверка логов vision

Если ingestion запускается через API (`/ingest/a/run`, `/ingest/b/run`), смотрим `support-api`:
```bash
docker compose logs -f support-api | rg vision_
```

Если ingestion запускается отдельными контейнерами (`docker compose run --rm ingest-a|ingest-b`), проверяем их:
```bash
docker compose logs ingest-a | rg "vision_|ingest_image_"
docker compose logs ingest-b | rg "vision_|ingest_image_"
```

Ожидаемые события: `vision_request_received`, `vision_image_processed`, `vision_request_finished`, `ingest_image_assets_processed` и ошибки OCR при проблемах.

### 9.4 Проверка того, что изображения извлеклись, OCR отработал и результаты сохранились

1) Валидация извлечённых изображений на диске:
```bash
find ./data/parsed_images/csv_ans_docs -type f | wc -l
find ./data/parsed_images/internal_regulations -type f | wc -l
```
Ожидаемо: значения больше `0` для наборов документов с embedded-картинками.

2) Валидация сохранённых image-derived чанков в Postgres:
```bash
docker compose exec -T postgres psql -U "${POSTGRES_USER:-support_user}" -d "${POSTGRES_DB:-support}" -c \
"SELECT source_type, COUNT(*) AS image_chunks FROM chunks WHERE chunk_id LIKE '%_img_%' GROUP BY source_type ORDER BY source_type;"
```
Ожидаемо: `image_chunks > 0`.

3) Быстрый просмотр примеров OCR-сохранений:
```bash
docker compose exec -T postgres psql -U "${POSTGRES_USER:-support_user}" -d "${POSTGRES_DB:-support}" -c \
"SELECT source_type, chunk_id, left(text_preview, 200) AS preview FROM chunks WHERE chunk_id LIKE '%_img_%' ORDER BY id DESC LIMIT 10;"
```
Ожидаемо: в `preview` присутствуют префиксы вида `[IMAGE] ... OCR:`.

4) Проверка, что OCR инициализировался с корректным режимом CPU/GPU:
```bash
docker compose logs support-api | rg "vision_ocr_initialized|vision_ocr_init_failed"
```
Ожидаемо: событие `vision_ocr_initialized` с полем `use_gpu=true|false`.

Если ingestion запускается `ingest-a/ingest-b`, используйте:
```bash
docker compose logs ingest-a | rg "vision_ocr_initialized|vision_ocr_init_failed"
docker compose logs ingest-b | rg "vision_ocr_initialized|vision_ocr_init_failed"
```

### 9.5 Автоматизированный регрессионный прогон (5 тест-кейсов)
Скрипт `scripts/run_vision_regression.py` автоматически:
- подготавливает контрольные картинки в `data/vision_regression/`;
- создаёт PDF с embedded-изображением в `data/inbox/csv_ans_docs/vision_regression_marker.pdf`;
- запускает 5 проверок (positive/negative) для `vision + OCR + retrieval`;
- возвращает код `0` при успехе и `1` при любом фейле.

Запуск:
```bash
python3 scripts/run_vision_regression.py --api-url http://localhost:8000
```

Опции:
```bash
python3 scripts/run_vision_regression.py --help
python3 scripts/run_vision_regression.py --marker-token ERR-9A7K-UNIQUE
python3 scripts/run_vision_regression.py --prefer-docker-for-assets
```

## 10) Типовые проблемы
- `vision_ocr_init_failed`: не найдены OCR-модели в `VISION_OCR_MODEL_ROOT`.
- `vision_ocr_init_failed` + `No module named 'paddle'`: отсутствует runtime-зависимость `paddlepaddle` в контейнерном окружении.
- Пустой `visual_evidence`: невалидный путь к изображению или OCR не смог извлечь текст.
- Нет image-derived чанков: проверьте, что `VISION_INGEST_ENABLED=true`, а также логи `ingest_image_assets_processed` и `ingest_image_chunks_empty_after_extraction`.

## 11) Логирование и мониторинг
Новая подсистема использует существующий контур:
- JSON-логи в stdout и файл `support-api.log`
- сбор Promtail
- хранение Loki
- визуализация в Grafana

Дополнительной отдельной logging-инфраструктуры не требуется.
