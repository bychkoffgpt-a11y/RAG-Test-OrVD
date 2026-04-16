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
      "page_number": 1
    }
  ]
}
```

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
      "ocr_text": "...",
      "summary": "...",
      "confidence": 0.91
    }
  ]
}
```

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

Возвращает:
- стандартное поле `choices`;
- дополнительные поля проекта: `sources`, `images`, `visual_evidence`.

Если текст вопроса отсутствует, но есть attachment, используется fallback-вопрос:
- `"Опишите, что видно на скриншоте, и предложите решение проблемы."`

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
