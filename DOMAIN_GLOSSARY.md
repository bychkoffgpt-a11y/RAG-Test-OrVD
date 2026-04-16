# DOMAIN_GLOSSARY.md

## Термины проекта

### Document
Исходный файл (PDF/DOCX/изображение), поступающий в ingestion.

### Source type
Тип корпуса документа: `csv_ans_docs` или `internal_regulations`.

### Chunk
Фрагмент документа после разбиения для индексации и retrieval.

### Embedding
Векторное представление чанка/запроса, используемое в Qdrant-поиске.

### Candidate pool
Расширенный набор кандидатов retrieval до reranking.

### Reranker
Модель, которая переупорядочивает retrieved-кандидаты по релевантности к вопросу.

### Top-k
Количество чанков, передаваемых в prompt (и/или возвращаемых retriever-ом).

### Grounded answer
Ответ, опирающийся на извлечённые источники, а не на догадки.

### SourceItem
API-сущность источника: `doc_id`, `source_type`, `page_number`, `chunk_id`, `score`, `image_paths`, `download_url`.

### Visual evidence
Структурированный результат обработки пользовательских изображений: OCR-текст + summary + confidence.

### Ingest A / Ingest B
Два независимых ingestion-пайплайна для разных корпусов документов.

## Предпочтительная терминология
- Использовать `retrieval`, а не абстрактное «поиск» без контекста.
- Использовать `grounded`, когда ответ подтверждён источниками.
- Использовать `source_type`, а не «база A/B» в API/коде.

## Термины, требующие уточнения
- `quality` — всегда с метрикой (например, Recall@k, MRR, доля grounded-ответов).
- `faster` — всегда с указанием p50/p95 latency.
- `better` — только вместе с baseline и результатом сравнения.
