# Тестирование и отладка из терминала

Документ описывает полезные команды для точечной проверки компонентов системы `RAG-Test-OrVD` через терминал.

## 0) Подготовка

```bash
# из корня репозитория
export API_URL="http://localhost:8000"

# опционально: jq для красивого вывода JSON
# sudo apt-get install -y jq
```

Проверка доступности API:

```bash
curl -sS "$API_URL/health" | jq
```

---

## 1) Задать системе вопрос (`/ask`)

```bash
curl -sS -X POST "$API_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Как подать заявку на доступ?",
    "scope": "all",
    "top_k": 8
  }' | jq
```

Полезно для проверки базового RAG-контура: retrieval + generation + sources.

---

## 2) Задать вопрос и передать картинку (`/ask` + attachments)

```bash
curl -sS -X POST "$API_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Что видно на скриншоте и как исправить ошибку?",
    "scope": "all",
    "top_k": 8,
    "attachments": [
      {
        "image_path": "/data/runtime_uploads/test.png",
        "page_number": 1
      }
    ]
  }' | jq
```

Смотрите поля `visual_evidence`, `images`, `sources`.

---

## 3) Распознать картинку через OpenAI-compatible endpoint (`/v1/chat/completions`)

### Вариант A: `file://`

```bash
curl -sS -X POST "$API_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local-rag",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "Опиши, что изображено"},
          {"type": "image_url", "image_url": {"url": "file:///data/runtime_uploads/test.png"}}
        ]
      }
    ],
    "temperature": 0.1,
    "max_tokens": 300
  }' | jq
```

### Вариант B: `data:image/...;base64,...`

```bash
IMG_B64=$(base64 -w 0 /path/to/local/test.png)
curl -sS -X POST "$API_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"local-rag\",
    \"messages\": [{
      \"role\": \"user\",
      \"content\": [
        {\"type\": \"text\", \"text\": \"Что на изображении?\"},
        {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/png;base64,${IMG_B64}\"}}
      ]
    }]
  }" | jq
```

---

## 4) Проверить включенный runtime-режим распознавания (`ocr|vlm`)

```bash
docker compose exec support-api sh -lc 'echo "VISION_RUNTIME_MODE=$VISION_RUNTIME_MODE"'
```

Дополнительно (сразу несколько важных параметров vision runtime):

```bash
docker compose exec support-api sh -lc '
  env | grep -E "^VISION_RUNTIME_MODE=|^VISION_RUNTIME_TIMEOUT_SEC=|^VISION_RUNTIME_MAX_IMAGES=|^VISION_RUNTIME_MAX_IMAGE_PIXELS="
'
```

---

## 5) Получить текущие параметры запущенной LLM

```bash
docker compose exec llm-server sh -lc '
  ps -eo pid,args | grep -E "llama-server|server" | grep -v grep
'
```

Команда обычно показывает фактические аргументы запуска (`-m`, `-c`, `-ngl`, `--host`, `--port`, `--metrics` и т.д.).

Проверка модели/контекста через `/props` (если endpoint доступен в вашей сборке llama.cpp):

```bash
curl -sS http://localhost:8080/props | jq
```

---

## 6) Получить текущие параметры запущенной VLM

```bash
docker compose exec support-api sh -lc '
  env | grep -E "^VISION_MODEL_PATH=|^VISION_MODEL_DEVICE=|^VISION_MODEL_DTYPE=|^VISION_MODEL_MAX_NEW_TOKENS=|^VISION_MODEL_PROMPT_RUNTIME=|^VISION_MODEL_PROMPT_INGEST="
'
```

Проверка выбранных режимов сразу для runtime и ingest:

```bash
docker compose exec support-api sh -lc 'env | grep -E "^VISION_RUNTIME_MODE=|^VISION_INGEST_MODE="'
```

---

## 7) Проверить наполнение PostgreSQL

### 7.1 Список таблиц

```bash
docker compose exec postgres psql -U rag -d rag -c "\dt"
```

### 7.2 Кол-во документов и чанков по корпусам (пример)

```bash
docker compose exec postgres psql -U rag -d rag -c '
SELECT source_type, COUNT(*) AS docs
FROM documents
GROUP BY source_type
ORDER BY source_type;
'
```

```bash
docker compose exec postgres psql -U rag -d rag -c '
SELECT source_type, COUNT(*) AS chunks
FROM chunks
GROUP BY source_type
ORDER BY source_type;
'
```

> Примечание: названия таблиц/полей могут отличаться в вашей схеме. Если запрос не сработал — сначала посмотрите `\dt` и `\d <table_name>`.

---

## 8) Проверить наполнение Qdrant

### 8.1 Список коллекций

```bash
curl -sS http://localhost:6333/collections | jq
```

### 8.2 Кол-во точек по коллекции

```bash
curl -sS http://localhost:6333/collections/csv_ans_docs | jq '.result | {name, points_count, vectors_count, indexed_vectors_count, status}'
```

```bash
curl -sS http://localhost:6333/collections/internal_regulations | jq '.result | {name, points_count, vectors_count, indexed_vectors_count, status}'
```

---

## 9) Дополнительные полезные запросы для отладки

### 9.1 Проверить наличие исходного документа по `doc_id`

```bash
curl -sS "$API_URL/sources/csv_ans_docs/<DOC_ID>/exists" | jq
```

### 9.2 Скачать исходный документ

```bash
curl -fSL "$API_URL/sources/csv_ans_docs/<DOC_ID>/download" -o /tmp/source_doc.bin
```

### 9.3 Запустить ingest корпуса A

```bash
curl -sS -X POST "$API_URL/ingest/a/run" | jq
```

### 9.4 Запустить ingest корпуса B

```bash
curl -sS -X POST "$API_URL/ingest/b/run" | jq
```

### 9.5 Проверить метрики support-api

```bash
curl -sS "$API_URL/metrics" | head -n 40
```

### 9.6 Проверить метрики llm-server

```bash
curl -sS http://localhost:8080/metrics | head -n 40
```

### 9.7 Логи support-api в реальном времени

```bash
docker compose logs -f support-api
```

### 9.8 Просмотр свежих trace-карточек RAG

```bash
find data/rag_traces/ui_requests -type f | tail -n 20
```

---

## 10) Типичный минимальный чек-лист после изменений

1. `curl /health` возвращает `ok`.
2. `/ask` без вложений возвращает `answer` и непустой `sources`.
3. `/ask` с вложением возвращает `visual_evidence`.
4. Включён ожидаемый `VISION_RUNTIME_MODE`.
5. В Qdrant есть точки в `csv_ans_docs` и `internal_regulations`.
6. В PostgreSQL есть документы/чанки по обоим корпусам.
