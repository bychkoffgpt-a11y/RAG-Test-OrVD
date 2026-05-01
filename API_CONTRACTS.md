# API_CONTRACTS.md

## Базовые endpoint'ы

### `POST /ask`
Синхронный RAG-запрос.

**Request (модель `AskRequest`):**
```json
{
  "question": "Как подать заявку?",
  "top_k": 8,
  "scope": "all",
  "attachments": [
    {
      "image_path": "/data/screenshot.png",
      "page_number": 1,
      "source_url": "https://example.local/screenshot.png?token=abc"
    }
  ]
}
```

Дополнительное мультимодальное поведение:
- если итоговый `answer` пустой, но `visual_evidence` содержит данные, возвращается непустой fallback, собранный из `ocr_text` и структурированных полей (`visible_facts`, `task_type`, `categories`).

Ограничения:
- `question`: обязательное поле, `min_length=3`.
- `scope`: `all | csv_ans_docs | internal_regulations`.

**Response (модель `AskResponse`):**
```json
{
  "answer": "...",
  "sources": [
    {
      "doc_id": "doc-123",
      "source_type": "csv_ans_docs",
      "page_number": 2,
      "chunk_id": "chunk-9",
      "score": 0.88,
      "image_paths": [],
      "download_url": "http://localhost:8000/sources/csv_ans_docs/doc-123/download"
    }
  ],
  "images": [],
  "visual_evidence": [
    {
      "image_path": "/data/screenshot.png",
      "source_url": "https://example.local/screenshot.png?token=abc",
      "ocr_text": "...",
      "summary": "...",
      "confidence": 0.91,
      "task_type": "text"
    }
  ]
}
```

Fallback-поведение:
- если итоговый `answer` пустой, но `visual_evidence` не пустой, endpoint формирует текстовый fallback из `ocr_text` и структурированных полей (`visible_facts`, `task_type`, `categories`).

Типовые ошибки:
- `504` — таймаут запроса к LLM backend.
- `502` — HTTP-ошибка LLM backend.
- `500` — внутренняя ошибка обработки.

---

### `POST /v1/chat/completions`
OpenAI-compatible endpoint.

Поддержка:
- `messages` (последнее user-сообщение используется как вопрос);
- `max_tokens` (default 1024), `temperature` (default 0.1), `stream`;
- image attachments в `content` (`image_url`, `input_image`, `image`).

Поведение для chart-кейсов:
- если `max_tokens` не передан и запрос распознан как chart/graph/diagram, используется сниженный бюджет генерации `VISION_CHART_RUNTIME_MAX_TOKENS` (по умолчанию `256`);
- для chart-кейсов в orchestration передаётся инструкция формировать краткий структурированный ответ без лишних объяснений.

Форматы image-вложений:
- `file:///...` (локальный путь в контейнере `support-api`, с учётом alias из `VISION_ATTACHMENT_PATH_ALIASES`);
- `data:image/<type>;base64,...` (будет материализовано во временный файл в `${FILE_STORAGE_ROOT}/runtime_uploads`);
- `http(s)://...` (изображение будет загружено и материализовано во временный файл в `${FILE_STORAGE_ROOT}/runtime_uploads`).

Ограничения image-вложений:
- максимальный размер: `VISION_ATTACHMENT_MAX_BYTES`;
- разрешённые MIME-типы: `VISION_ATTACHMENT_ALLOWED_MIME_TYPES`.
- лимит количества изображений в runtime-запросе: `VISION_RUNTIME_MAX_IMAGES` (`0` = без лимита);
- лимит пикселей на изображение (`width*height`): `VISION_RUNTIME_MAX_IMAGE_PIXELS` (`0` = без лимита);
- общий timeout runtime vision stage: `VISION_RUNTIME_TIMEOUT_SEC` (`0` = без лимита).

Возвращает:
- стандартное поле `choices`;
- дополнительные поля проекта: `sources`, `images`, `visual_evidence`.

Если текст вопроса отсутствует, но есть attachment, используется fallback-вопрос:
- `"Опишите, что видно на скриншоте, и предложите решение проблемы."`

---

### `POST /vision/debug/recognize`
Диагностический endpoint для отладки runtime-распознавания (VLM/OCR) без RAG retrieval.

Поведение:
- принимает prompt только извне (сервер не подставляет fallback prompt);
- поддерживает chart-case детекцию, как `/v1/chat/completions`;
- ответ формируется той же визуальной веткой, что и в chat (`visual_evidence` + генерация финального текста).

**Request:**
```json
{
  "prompt": "Проанализируй изображение, распознай весь текст...",
  "attachments": [
    {
      "image_path": "/data/screenshot.png"
    }
  ],
  "max_tokens": 1024,
  "temperature": 0.1,
  "task_type": "text"
}
```

- `task_type` (optional): принудительный тип задачи (`text|chart|sign`), если нужно отключить авто-детект по prompt.

**Response:**
```json
{
  "answer": "...",
  "visual_evidence": [
    {
      "image_path": "/data/screenshot.png",
      "ocr_text": "...",
      "summary": "...",
      "confidence": 0.91,
      "task_type": "text"
    }
  ],
  "chart_mode": false
}
```

---

### `POST /ingest/a/run`
Запускает ingestion корпуса A (`/data/inbox/csv_ans_docs`).

**Response (`IngestResponse`):**
```json
{
  "source_type": "csv_ans_docs",
  "processed_files": 12,
  "created_points": 430,
  "diagnostics": {
    "total_image_assets": 20,
    "total_image_points": 18,
    "total_image_assets_without_chunks": 2
  },
  "message": "ok"
}
```

### `POST /ingest/b/run`
Запускает ingestion корпуса B (`/data/inbox/internal_regulations`).

**Response (`IngestResponse`):**
```json
{
  "source_type": "internal_regulations",
  "processed_files": 12,
  "created_points": 430,
  "diagnostics": {
    "total_image_assets": 20,
    "total_image_points": 18,
    "total_image_assets_without_chunks": 2
  },
  "message": "ok"
}
```

---

### `GET /sources/{source_type}/{doc_id}/download`
Скачивание исходного документа по источнику из ответа.

### `GET /sources/{source_type}/{doc_id}/exists`
Диагностический endpoint: проверка наличия документа и числа чанков.

## Политика совместимости
- Обратная совместимость обязательна по умолчанию.
- Изменения формата `AskRequest`/`AskResponse` и `/v1/chat/completions` — только с документированием в changelog и обновлением integration-тестов.


## Vision summary behavior
- `visual_evidence[].summary` remains a diagnostic field for OCR/VLM processing.
- By default, `summary` is **not** appended to the final `answer` text.
- Backward compatibility flag: `VISION_INCLUDE_SUMMARY_IN_ANSWER=false` (default).
