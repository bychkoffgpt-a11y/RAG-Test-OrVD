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
- `--mode offline` (по умолчанию): в `app/wheels` должен быть полный набор wheel для всех прямых и транзитивных зависимостей.
- `--mode online`: пустой wheelhouse допустим, зависимости можно поставить из PyPI.
- `--online-strict-wheels`: дополнительно к `--mode online` требует полный wheelhouse (для запуска без fallback в PyPI).

Примеры:
```bash
./scripts/preflight_check.sh --mode offline
./scripts/preflight_check.sh --mode online
./scripts/preflight_check.sh --mode online --online-strict-wheels
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
7. Автоматически определяет, нужен ли rebuild `support-api`:
   - если изменились входы образа (`app/Dockerfile`, `app/pyproject.toml`, `app/src/**`, `app/wheels/**`, `docker-compose.yml`, `.env.example`) или образ отсутствует локально — запускает `docker compose up -d --build`;
   - иначе — запускает `docker compose up -d` без пересборки.

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

Для ускорения и предсказуемости online-сборки рекомендуется strict-режим wheelhouse:
```bash
./scripts/update_wheels.sh --mode refresh --strict
./scripts/update_app.sh --mode online --online-strict-wheels
```

## Устойчивость сборки Python-зависимостей и офлайн-режим

### Вариант 1 — онлайн-сборка (по умолчанию)
- При `docker compose build`/`up --build` используется `pip install` с повышенными retry/timeout.
- Этот режим требует доступ к PyPI.
- В режиме online используется `PIP_MODE=online`: при наличии `app/wheels/*.whl` сначала пробуется локальный wheelhouse.
- Если задан `PIP_ONLINE_FALLBACK=0` (или `./scripts/update_app.sh --online-strict-wheels`), fallback на PyPI отключается и сборка падает при неполном wheelhouse.
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
   ./scripts/update_wheels.sh --mode refresh --strict
   ```
   Либо (если нужно добавить dev-зависимости):
   ```bash
   ./scripts/update_wheels.sh --mode refresh --include-dev
   ```
2. (Опционально) инкрементально докачать missing wheels:
   ```bash
   ./scripts/update_wheels.sh --mode append
   ```
3. Скопировать каталог `app/wheels` в офлайн-контур (если сборка выполняется на другом хосте).
4. Запустить пересборку:
   ```bash
   docker compose build --no-cache ingest-a support-api
   ```
5. Убедиться, что зависимости ставятся из `/wheels` (в логах pip будет `--no-index --find-links=/wheels`).
   При ручном запуске можно явно зафиксировать офлайн-режим:
   ```bash
   PIP_MODE=offline docker compose build --no-cache support-api
   ```

Ранее используемая ручная команда `pip download ...` по списку пакетов всё ещё допустима, но рекомендуется именно `scripts/update_wheels.sh`: скрипт формирует список из `pyproject.toml`, валидирует транзитивные зависимости, поддерживает strict-режим и атомарно заменяет wheelhouse.

## Кэширование сборки Docker (BuildKit local cache)

Для сервисов `support-api` и `ingest-*` в `docker-compose.yml` включены `cache_from/cache_to` в локальный каталог `.docker-cache/`.
Это ускоряет повторные сборки после `git pull`, особенно при неизменных слоях зависимостей.

Рекомендации:
- Не удаляйте `.docker-cache/` между обычными обновлениями.
- Для «чистой» диагностики кэша можно временно удалить каталог:
  ```bash
  rm -rf .docker-cache
  ```

Пример старого ручного варианта:
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

## Профили чанкинга: управление, тюнинг и эксплуатация

Начиная с текущей версии, пайплайны A/B используют разные профили чанкинга.
Это позволяет раздельно оптимизировать поиск по «процедурной» документации и по нормативным текстам.

### Параметры в `.env`

```bash
# Корпус A (документация ЦСВ АНС)
CHUNK_SIZE_CSV_ANS_DOCS=1100
CHUNK_OVERLAP_CSV_ANS_DOCS=150
CHUNK_STRATEGY_CSV_ANS_DOCS=docs

# Корпус B (нормативные документы)
CHUNK_SIZE_INTERNAL_REGULATIONS=700
CHUNK_OVERLAP_INTERNAL_REGULATIONS=160
CHUNK_STRATEGY_INTERNAL_REGULATIONS=regs
```

Допустимые стратегии:
- `docs` — профиль для инструкций/руководств, с приоритетом заголовков и тематических блоков.
- `regs` — профиль для нормативных документов, с приоритетом пунктов/подпунктов.
- `fixed` — fallback-режим (сплошная нарезка с overlap без структурного разбиения).

### Как профиль применяется в пайплайне
1. Ingest-процесс (`ingest-a`/`ingest-b`) считывает параметры из ENV.
2. Пайплайн вызывает chunker c нужной стратегией и лимитами.
3. Для каждого чанка вычисляется embedding и сохраняется payload в Qdrant.
4. В payload добавляются служебные поля:
   - `section_title`;
   - `clause_ref` (в первую очередь полезно для `regs`).

### Рекомендации по стартовым значениям
- Документация ЦСВ АНС:
  - `chunk_size` 1000–1200
  - `overlap` 120–180
  - `strategy=docs`
- Нормативные документы:
  - `chunk_size` 550–800
  - `overlap` 120–200
  - `strategy=regs`

### Когда менять параметры

Признаки, что `chunk_size` слишком большой:
- в источниках часто смешиваются разные темы в одном чанке;
- ухудшается точность ответа на узкий вопрос.

Признаки, что `chunk_size` слишком маленький:
- ответы теряют контекст между соседними фразами/условиями;
- LLM чаще «склеивает» фрагменты с неточностями.

Признаки, что `overlap` слишком маленький:
- обрывы по границам пунктов;
- ошибки на вопросах с отсылками к «предыдущему пункту».

Признаки, что `overlap` слишком большой:
- рост числа почти дублирующихся чанков;
- лишняя нагрузка на индексацию/хранилище.

### Безопасная процедура изменения чанкинга
1. Изменить параметры в `.env`.
2. Переиндексировать только нужный корпус:
   - `docker compose run --rm ingest-a`
   - `docker compose run --rm ingest-b`
3. Проверить логи и объём созданных чанков.
4. Прогнать контрольный список вопросов (smoke set) по обоим корпусам.

### Минимальный чеклист после изменения
- [ ] ingestion завершился без ошибок;
- [ ] число чанков изменилось ожидаемо (без аномалий x5/x10);
- [ ] ответы по контрольным вопросам не деградировали по точности источников;
- [ ] в источниках видны релевантные `section_title`/`clause_ref` (если используете отладочную выдачу).

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

### 6) Проверить поведение при `stream=true`
OpenAI-compatible endpoint поддерживает SSE-стриминг (`text/event-stream`): при `"stream": true` backend отправляет чанки `chat.completion.chunk` и финальный маркер `data: [DONE]`.

Проверка:
```bash
curl -N -sS http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"local-rag-model","stream":true,"messages":[{"role":"user","content":"Кто ты?"}]}'
```

Ожидаемо: в ответе идут несколько строк `data: ...`, последняя — `data: [DONE]`.

## Проверка модельных артефактов перед запуском
- Проверить наличие LLM: `test -f models/llm/qwen2.5-7b-instruct-q4_k_m.gguf && echo OK`
- Проверить embeddings: `test -f models/embeddings/bge-m3/config.json && echo OK`
- Проверить reranker: `test -f models/reranker/bge-reranker-v2-m3/config.json && echo OK`
- Эталон версий: `docs/model_registry.md`

## Бэкап
1. Экспорт БД и файлов: `./scripts/backup_all.sh --mode offline`
2. Восстановление: `./scripts/restore_all.sh --mode offline data/backups/<timestamp>`
