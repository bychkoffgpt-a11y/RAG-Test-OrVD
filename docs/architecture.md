# Архитектура офлайн-системы поддержки ЦСВ АНС

## Цели
- Полностью локальная работа без интернета и облаков.
- Ответы с опорой на источники из двух независимых корпусов документов.
- Поддержка форматов DOC/DOCX/PDF.
- Возврат текста ответа и списка источников; поле `images` в API предусмотрено, но в текущем пайплайне парсеры не извлекают изображения из DOCX/PDF.
- Полноценная система логирования и мониторинга с первого дня.

## Ключевые компоненты

### Готовые OSS-компоненты
- Open WebUI — интерфейс чата.
- llama.cpp server — локальный инференс LLM.
- Qdrant — векторная БД.
- PostgreSQL — метаданные документов, чанков и аудит.
- Prometheus + Grafana — метрики.
- Loki + Promtail — сбор и поиск логов.

### Кастомные компоненты (Python)
- `support-api` (FastAPI):
  - маршруты `/ask`, `/ingest/a/run`, `/ingest/b/run`;
  - OpenAI-compatible endpoint `/v1/chat/completions`;
  - оркестрация retrieval + LLM.
- Ingestion pipeline A/B:
  - раздельная обработка документации ЦСВ АНС и нормативных документов;
  - chunking, эмбеддинги, upsert в Qdrant;
  - запись метаданных в PostgreSQL.

## Модельный стек (зафиксирован)
- LLM: `qwen2.5-7b-instruct-q4_k_m.gguf` (через llama.cpp server).
- Embeddings: `BAAI/bge-m3`.
- Reranker: `BAAI/bge-reranker-v2-m3` (артефакт обязателен по preflight, но в текущем retrieval-пайплайне не используется).
- Источник правды по артефактам и правилам версионирования: [Реестр моделей](model_registry.md).

## Разделение данных
- Коллекция Qdrant `csv_ans_docs`.
- Коллекция Qdrant `internal_regulations`.
- Физическое хранение файлов на диске в `./data`.

## Логирование и мониторинг
- JSON-логи приложения пишутся в stdout и `app/logs/support-api.log`.
- Promtail читает контейнерные логи Docker и файл логов API.
- Loki агрегирует логи.
- Grafana подключена к Loki и Prometheus.
