# Эксплуатация

> Документ предполагает, что Docker уже установлен и доступен в текущем shell. Перед выполнением команд проверьте:
> ```bash
> docker --version
> docker compose version
> ```
> Если проверки не проходят, сначала выполните шаги подготовки из [`docs/deployment_wsl2.md`](deployment_wsl2.md#1-предварительные-условия).

## Предпусковая проверка (рекомендуется перед каждым запуском)
```bash
./scripts/preflight_check.sh --mode offline
```

Скрипт поддерживает 2 режима:
- `--mode offline` (по умолчанию): в `app/wheels` должен быть хотя бы один `*.whl`.
- `--mode online`: пустой wheelhouse допустим, зависимости можно поставить из PyPI.

Примеры:
```bash
./scripts/preflight_check.sh --mode offline
./scripts/preflight_check.sh --mode online
```

Если Docker временно недоступен в shell (например, в CI lint-этапе), можно выполнить только файловую/ENV-проверку:
```bash
./scripts/preflight_check.sh --mode offline --skip-docker
```

## Автотесты и merge-политика

### Локальный запуск (обязательно перед merge)
```bash
cd app
pip install -e .[dev]
pytest -q --cov=src --cov-report=term-missing
```

### Что считается «перед merge в GitHub»
- Ветка обновлена и не конфликтует с целевой.
- Локально выполнен полный запуск автотестов без падений.
- В PR прошёл GitHub Actions workflow `tests`.

Рекомендация: включить в настройках репозитория обязательный status check `tests` для ветки `main`.

## Базовые команды
- Запуск: `docker compose up -d`
- Остановка: `docker compose down`
- Статус: `docker compose ps`
- Логи API: `docker compose logs -f support-api`

## Безопасное обновление и перезапуск приложения
> Рекомендуемый способ обновления — скрипт `scripts/update_app.sh`.

Запуск:
```bash
./scripts/update_app.sh --mode offline
```

Что делает скрипт:
1. Проверяет, что рабочее дерево Git чистое (нет `staged`/`unstaged` изменений).
2. Проверяет, что запуск идёт из Git-ветки с настроенным `upstream`.
3. Полностью останавливает стек (`docker compose down --remove-orphans`).
4. Выполняет `git fetch --all --prune`.
5. Выполняет `git pull --ff-only`.
6. Запускает `./scripts/preflight_check.sh --mode <offline|online>`.
7. Поднимает приложение (`docker compose up -d --build`).

Если нужен «чистый» старт с удалением данных, перед этим выполните отдельно:
```bash
docker compose down -v
```

Ручной сценарий (если нужен полный контроль шагов):
```bash
docker compose down --remove-orphans
git fetch --all --prune
git pull --ff-only
./scripts/preflight_check.sh --mode offline
docker compose up -d --build
```

Для контура с интернетом можно явно запускать в online-режиме:
```bash
./scripts/update_app.sh --mode online
```

## Устойчивость сборки Python-зависимостей и офлайн-режим

### Вариант 1 — онлайн-сборка (по умолчанию)
- При `docker compose build`/`up --build` используется `pip install` с повышенными retry/timeout.
- Этот режим требует доступ к PyPI.
- В режиме online принудительно используется `PIP_MODE=online`, поэтому даже при наличии `app/wheels/*.whl` зависимости ставятся из индекса (это защищает от падения на неполном wheelhouse).
- Перед установкой выполняется TLS precheck к `pypi.org:443`; при проблемах выводится явная диагностика по сети/сертификатам.
- Можно использовать кастомный индекс/зеркало через build args:
  ```bash
  docker compose build support-api \
    --build-arg PIP_MODE=online \
    --build-arg PIP_INDEX_URL=https://pypi.org/simple \
    --build-arg PIP_EXTRA_INDEX_URL= \
    --build-arg PIP_TRUSTED_HOST=
  ```

### Вариант 2 — полностью офлайн (рекомендуется для закрытого контура)
1. На машине с интернетом подготовить wheelhouse:
   ```bash
   cd app
   mkdir -p wheels
   pip download -d wheels \
     fastapi==0.115.0 \
     uvicorn[standard]==0.30.6 \
     pydantic==2.9.2 \
     pydantic-settings==2.5.2 \
     httpx==0.27.2 \
     qdrant-client==1.11.3 \
     sentence-transformers==3.2.0 \
     python-multipart==0.0.12 \
     python-docx==1.1.2 \
     pypdf==5.0.1 \
     prometheus-client==0.21.0 \
     psycopg[binary]==3.2.3 \
     setuptools>=68 \
     wheel
   ```
2. Скопировать каталог `app/wheels` в офлайн-контур (если сборка выполняется на другом хосте).
3. Запустить пересборку:
   ```bash
   docker compose build --no-cache ingest-a support-api
   ```
4. Убедиться, что зависимости ставятся из `/wheels` (в логах pip будет `--no-index --find-links=/wheels`).
   При ручном запуске можно явно зафиксировать офлайн-режим:
   ```bash
   PIP_MODE=offline docker compose build --no-cache support-api
   ```

## Где размещать документы
- Корпус A: `data/inbox/csv_ans_docs`
- Корпус B: `data/inbox/internal_regulations`

## Подготовка документов к индексации
### Поддерживаемые форматы
- `.doc`
- `.docx`
- `.pdf`

### Ограничения и особенности
- `.doc` автоматически конвертируется в `.docx` через LibreOffice (`soffice`) в ingest-пайплайне.
- Для `.pdf` используется извлечение текстового слоя; OCR в текущем ingest-пайплайне не выполняется автоматически.
- Отсканированные PDF без текстового слоя нужно заранее прогонять через OCR отдельным процессом.
- PDF с паролем/шифрованием и повреждённые файлы могут не индексироваться.

### Практические рекомендации перед запуском
- Проверить, что файлы лежат в правильных директориях корпусов (A/B).
- Нормализовать имена файлов (избегать спецсимволов и неоднозначных дубликатов).
- Убедиться, что `.doc`/`.docx` открываются без ошибок.
- Для сканов PDF — предварительно выполнить OCR и сохранить PDF с текстовым слоем.

### Мини-чеклист перед индексацией
- [ ] Все файлы разложены по нужным каталогам A/B.
- [ ] Используются только `.doc`, `.docx`, `.pdf`.
- [ ] Для PDF подтверждено наличие текстового слоя.
- [ ] Нет зашифрованных/повреждённых файлов.

## Индексация
- Контур A: `docker compose run --rm ingest-a`
- Контур B: `docker compose run --rm ingest-b`

## Проверка интеграции
- API health: `curl http://localhost:8000/health`
- Список моделей (OpenAI-compatible): `curl http://localhost:8000/v1/models`
- Метрики: `curl http://localhost:8000/metrics`
- Qdrant: `curl http://localhost:6333/healthz`
- Loki ready: `curl http://localhost:3100/ready`

Если в Open WebUI появляется ошибка `Модель не выбрана`:
1. Проверьте, что `curl http://localhost:8000/v1/models` возвращает непустой массив `data`.
2. В интерфейсе Open WebUI выберите модель `local-rag-model` в селекторе модели перед первым вопросом.

## Диагностика зависания ответа ("крутится 10+ минут")

Ниже быстрый runbook для случая, когда в Open WebUI сообщение долго находится в состоянии генерации.

### 1) Проверить базовую доступность API и модели
```bash
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/v1/models
```

Ожидается `status=ok` и модель `local-rag-model` в `data`.

### 2) Проверить прямой вызов OpenAI-compatible endpoint
```bash
curl -sS http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"local-rag-model","stream":false,"messages":[{"role":"user","content":"Кто ты?"}]}'
```

Если этот запрос тоже зависает — проблема в backend-пайплайне (retrieval/LLM), а не в UI.

### 3) Проверить, где именно висит пайплайн по логам support-api
```bash
docker compose logs -f support-api | rg -n "rag_|retriever_|qdrant_|embedding_model|openai_compat_generation_params|request completed"
```

Ориентиры:
- `embedding_model_load_started` без `embedding_model_load_finished` — проблема загрузки embedding-модели.
- Есть `rag_prompt_built`, но нет `rag_llm_finished` — зависание на LLM (`llm-server`).
- `retriever_collection_failed` — проблемы с Qdrant/коллекцией.

### 4) Проверить доступность llama.cpp server и Qdrant
```bash
curl -sS http://localhost:8080/health
curl -sS http://localhost:6333/healthz
docker compose logs --tail=200 llm-server
docker compose logs --tail=200 qdrant
```

### 5) Проверить корректность локальных артефактов embedding
```bash
test -f models/embeddings/bge-m3/config.json && echo "embeddings OK"
```

При отсутствии файла API теперь завершается с явной ошибкой и не пытается молча "докачивать" модель.

### 6) Проверить, что клиент не запрашивает stream=true
Для данного backend потоковый ответ пока не поддержан. Если клиент отправляет `"stream": true`, API вернёт `400` с пояснением.

## Проверка модельных артефактов перед запуском
- Проверить наличие LLM: `test -f models/llm/qwen2.5-7b-instruct-q4_k_m.gguf && echo OK`
- Проверить embeddings: `test -f models/embeddings/bge-m3/config.json && echo OK`
- Проверить reranker: `test -f models/reranker/bge-reranker-v2-m3/config.json && echo OK`
- Эталон версий: `docs/model_registry.md`

## Бэкап
1. Экспорт БД и файлов: `./scripts/backup_all.sh --mode offline`
2. Восстановление: `./scripts/restore_all.sh --mode offline data/backups/<timestamp>`
