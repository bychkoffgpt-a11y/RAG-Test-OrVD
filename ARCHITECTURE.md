# ARCHITECTURE.md

## 1) Overview
`RAG-Test-OrVD` — офлайн RAG-система поддержки, которая работает локально и объединяет:
- ingestion двух корпусов документов;
- retrieval из Qdrant;
- генерацию ответа через локальный LLM backend;
- мультимодальную обработку изображений (OCR + visual summary);
- возврат источников с `download_url`.

## 2) Основной поток данных
1. Документы поступают в `data/inbox/<source_type>`.
2. `pipeline_a`/`pipeline_b` парсят DOCX/PDF/изображения, выполняют chunking и дедупликацию.
3. Эмбеддинги чанков (включая OCR-текст изображений из документов) пишутся в Qdrant
   (`csv_ans_docs`, `internal_regulations`), метаданные — в PostgreSQL.
4. Пользовательский вопрос (+ опциональные вложения) приходит в `/ask` или `/v1/chat/completions`.
5. Если переданы изображения: VisionService выполняет OCR/VLM-анализ →
   извлечённый `ocr_text` **дополняет вопрос** для построения embedding-вектора
   (OCR-augmented retrieval). Это позволяет находить документы, релевантные
   содержимому скриншота, а не только тексту вопроса.
6. Retriever выбирает кандидатов по OCR-augmented вектору, reranker (если включён)
   уточняет ранжирование.
7. Prompt builder формирует контекст: retrieved chunks + секция `visual_evidence`
   с OCR-текстом и summary изображений.
8. LLM генерирует ответ, учитывая и документы, и содержимое скриншота.
9. API возвращает answer + sources с `download_url` (+ images/visual_evidence при мультимодальности).

## 3) Ключевые сервисы и модули
- `support-api` (`app/src/main.py`): HTTP API, совместимость с OpenAI форматом, middleware/метрики.
- `rag/*`: orchestration, retrieval, prompt assembly, answer formatting.
- `ingest/*`: ingestion pipelines A/B и парсинг документов.
- `storage/*`: доступ к Qdrant/PostgreSQL.
- `vision/service.py`: OCR + visual analysis для вложений пользователя.
- `vision/service.py`: переключаемые режимы `ocr|vlm` отдельно для runtime и ingest.
- `telemetry/metrics.py`: метрики Prometheus.

## 4) Разделение корпусов
- Корпус A: `csv_ans_docs` (документация/процедуры), крупнее chunk.
- Корпус B: `internal_regulations` (нормативные документы), более мелкий chunk и больший overlap.

Актуальные defaults задаются через env в `app/src/core/settings.py`:
- A: `chunk_size_csv_ans_docs=1100`, `chunk_overlap_csv_ans_docs=150`, strategy `docs`.
- B: `chunk_size_internal_regulations=700`, `chunk_overlap_internal_regulations=160`, strategy `regs`.

## 5) Нефункциональные требования
- Offline-first: без обязательных внешних облачных API.
- Наблюдаемость: JSON-логи + Prometheus + Grafana + Loki/Promtail.
- Воспроизводимость: фиксированные версии зависимостей в `app/pyproject.toml`.
- Совместимость API: сохранение контрактов `/ask` и `/v1/chat/completions`.

## 6) Точки расширения
- Retrieval: фильтры, гибридный поиск, reranker tuning.
- Prompting: изменение системных инструкций и формата ответа.
- Ingestion: поддержка новых форматов документов/источников.
- Vision: улучшение OCR и confidence-логики.
