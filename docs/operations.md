# Эксплуатация

> Документ предполагает, что Docker уже установлен и доступен в текущем shell. Перед выполнением команд проверьте:
> ```bash
> docker --version
> docker compose version
> ```
> Если проверки не проходят, сначала выполните шаги подготовки из [`docs/deployment_wsl2.md`](deployment_wsl2.md#1-предварительные-условия).

## Предпусковая проверка (рекомендуется перед каждым запуском)
```bash
./scripts/preflight_check.sh
```

Если Docker временно недоступен в shell (например, в CI lint-этапе), можно выполнить только файловую/ENV-проверку:
```bash
./scripts/preflight_check.sh --skip-docker
```

## Базовые команды
- Запуск: `docker compose up -d`
- Остановка: `docker compose down`
- Статус: `docker compose ps`
- Логи API: `docker compose logs -f support-api`

## Полная остановка и «чистый» перезапуск после обновления проекта
> Используйте этот сценарий, когда нужно гарантированно остановить весь стек, подтянуть изменения файлов проекта и запустить всё заново.

1. Остановить и удалить контейнеры проекта:
   ```bash
   docker compose down
   ```
2. (Опционально) удалить также тома данных, если нужен запуск «с нуля» без старых индексов/БД:
   ```bash
   docker compose down -v
   ```
3. (Опционально) удалить локальные образы проекта, чтобы пересобрать их полностью:
   ```bash
   docker compose down --rmi local
   ```
4. Обновить файлы проекта из Git:
   ```bash
   git fetch --all --prune
   git pull --ff-only
   ```
5. Проверить/обновить `.env` при изменениях переменных:
   ```bash
   cp -n .env.example .env
   ```
6. Выполнить предпусковую проверку:
   ```bash
   ./scripts/preflight_check.sh
   ```
7. Поднять стек заново с пересборкой:
   ```bash
   docker compose up -d --build
   ```
8. Проверить состояние:
   ```bash
   docker compose ps
   docker compose logs -f support-api
   ```

## Устойчивость сборки Python-зависимостей и офлайн-режим

### Вариант 1 — онлайн-сборка (по умолчанию)
- При `docker compose build`/`up --build` используется `pip install` с повышенными retry/timeout.
- Этот режим требует доступ к PyPI.

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
- Метрики: `curl http://localhost:8000/metrics`
- Qdrant: `curl http://localhost:6333/healthz`
- Loki ready: `curl http://localhost:3100/ready`

## Проверка модельных артефактов перед запуском
- Проверить наличие LLM: `test -f models/llm/qwen2.5-7b-instruct-q4_k_m.gguf && echo OK`
- Проверить embeddings: `test -f models/embeddings/bge-m3/config.json && echo OK`
- Проверить reranker: `test -f models/reranker/bge-reranker-v2-m3/config.json && echo OK`
- Эталон версий: `docs/model_registry.md`

## Бэкап
1. Экспорт БД и файлов: `./scripts/backup_all.sh`
2. Восстановление: `./scripts/restore_all.sh data/backups/<timestamp>`
