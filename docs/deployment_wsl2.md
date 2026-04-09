# Пошаговая инструкция развёртывания (WSL2, одна ВМ, офлайн)

> Цель: развернуть полностью локальную систему чат-поддержки ЦСВ АНС на одной WSL2-машине с Docker и GPU.

## 1. Предварительные условия

## 1.1. Требования к хосту (Windows)
1. Windows 11 (рекомендуется актуальная сборка).
2. Установленный драйвер NVIDIA с поддержкой WSL2 CUDA.
3. Включённые компоненты:
   - Windows Subsystem for Linux;
   - Virtual Machine Platform.
4. Docker Desktop с включённой интеграцией WSL2.

## 1.2. Требования к WSL2-дистрибутиву
- Ubuntu 24.04 (рекомендуется).
- Доступно не менее 200 ГБ свободного места (модели + индексы + логи).

---

## 2. Подготовка WSL2

1. Обновите систему:
```bash
sudo apt update && sudo apt upgrade -y
```

2. Установите утилиты:
```bash
sudo apt install -y git curl jq unzip
```

3. Проверьте доступность Docker CLI внутри WSL2:
```bash
docker --version
docker compose version
```

Если команда `docker` не найдена:
1. Установите/запустите Docker Desktop в Windows.
2. Включите WSL Integration для вашего дистрибутива в Docker Desktop.
3. Перезапустите Docker Desktop, затем выполните `wsl --shutdown` и снова откройте WSL.
4. Повторите проверки `docker --version` и `docker compose version`.

4. Клонируйте репозиторий:
```bash
git clone https://github.com/bychkoffgpt-a11y/RAG-Test-OrVD
cd RAG-Test-OrVD
```

5. Подготовьте структуру проекта:
```bash
./scripts/bootstrap_offline.sh --mode offline
cp .env.example .env
```

6. Заполните `.env` актуальными паролями.

7. Выполните предпусковую проверку конфигурации и артефактов:
```bash
./scripts/preflight_check.sh --mode offline
```

---

## 3. Проверки GPU (обязательно)

> Обязательное требование для запуска `llm-server`: сервис должен стартовать с `gpus: all` в `docker-compose.yml`; `NVIDIA_VISIBLE_DEVICES` и `NVIDIA_DRIVER_CAPABILITIES` должны быть заданы, но этого недостаточно без `gpus: all`.
> На старте `llm-server` не выполняется принудительный fallback на CPU при неоднозначной детекции GPU: сохраняется конфигурация `LLM_N_GPU_LAYERS`, а диагностика делается через `nvidia-smi` и логи llama.cpp.

## 3.1. Проверка в Windows (PowerShell)
```powershell
nvidia-smi
```
Ожидаемо: корректно определяется видеокарта RTX.

## 3.2. Проверка внутри WSL2
```bash
nvidia-smi
```
Ожидаемо: та же видеокарта видна в Linux-среде.

## 3.3. Проверка GPU внутри Docker
```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```
Ожидаемо: `nvidia-smi` выводит данные о GPU.

Если шаг 3.3 не проходит:
1. Проверьте, что Docker Desktop запущен.
2. В Docker Desktop включена WSL integration для вашего дистрибутива.
3. Обновите драйвер NVIDIA и перезапустите Windows.

---

## 4. Подготовка офлайн-артефактов

> Для air-gap среды образы и модели должны быть заранее загружены в локальное хранилище/архив.

## 4.1. Зафиксируйте версии моделей

Используйте только следующий стек:
- LLM (GGUF): `qwen2.5-7b-instruct-q4_k_m.gguf`
- Embeddings: `BAAI/bge-m3`
- Reranker: `BAAI/bge-reranker-v2-m3`

Подробная матрица артефактов: [`docs/model_registry.md`](model_registry.md).

## 4.2. Подготовьте и поместите модели

Разместите артефакты строго по путям:
- `models/llm/qwen2.5-7b-instruct-q4_k_m.gguf`
- `models/embeddings/bge-m3/`
- `models/reranker/bge-reranker-v2-m3/`

> В этом репозитории нет автоскачивания моделей: загрузка выполняется заранее во внутренний офлайн-архив/registry, затем артефакты копируются в `models/`.

## 4.3. (Рекомендуется) Проверка контрольных сумм

1. Заполните в `.env` значения:
   - `LLM_MODEL_SHA256`
   - `EMBEDDING_MODEL_SHA256`
   - `RERANKER_MODEL_SHA256`
2. Проверьте SHA256 локально:
```bash
sha256sum models/llm/qwen2.5-7b-instruct-q4_k_m.gguf
```
3. Сверьте с эталонными суммами из вашего доверенного офлайн-источника.

## 4.4. Подготовьте документы
- Документация ЦСВ АНС: `data/inbox/csv_ans_docs`
- Нормативные документы: `data/inbox/internal_regulations`
- Поддерживаемые форматы: `.doc`, `.docx`, `.pdf`
- Для PDF нужен текстовый слой (сканы без текста заранее обрабатывайте OCR отдельно)

Подробные эксплуатационные правила подготовки: [`docs/operations.md`](operations.md#подготовка-документов-к-индексации).

---

## 5. Запуск системы

1. Выполните предпусковую проверку:
```bash
./scripts/preflight_check.sh --mode offline
```

2. Поднимите сервисы:
```bash
docker compose up -d postgres qdrant llm-server support-api openwebui prometheus loki promtail grafana
```

3. Проверьте статус:
```bash
docker compose ps
```

4. Проверьте доступность:
```bash
curl http://localhost:8000/health
curl http://localhost:6333/healthz
curl http://localhost:3100/ready
curl http://localhost:9090/-/healthy
```

5. Выполните первичную индексацию:
```bash
docker compose run --rm ingest-a
docker compose run --rm ingest-b
```

---

## 6. Проверка функционала чат-бота

1. Откройте Open WebUI: `http://localhost:3000`
2. Проверьте ответ через API:
```bash
curl -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Как войти в систему ЦСВ АНС?", "top_k":5, "scope":"all"}'
```

Ожидаемо:
- поле `answer`;
- массив `sources` (включая `download_url` для каждого источника);
- массив `images` (может быть пустым, если в источниках нет картинок).

Проверка скачивания документа-источника:
```bash
curl -OJ http://localhost:8000/sources/csv_ans_docs/<DOC_ID>/download
```

---

## 7. Логирование и мониторинг (полный контур)

## 7.1. Куда писать/смотреть
- Grafana: `http://localhost:3101`
- Prometheus: `http://localhost:9090`
- Loki API: `http://localhost:3100`

## 7.2. Что логируется
- Контейнерные логи (через Promtail).
- JSON-логи приложения `support-api`.

## 7.3. Базовые проверки логов
```bash
docker compose logs --tail=200 support-api
docker compose logs --tail=200 promtail
docker compose logs --tail=200 loki
```

## 7.4. Преднастроенные alert-шаблоны Grafana (warning/error по всем сервисам)
- Alert-правила provisioned из файла `infra/grafana/provisioning/alerting/log-severity-rules.yaml`.
- Правила создаются автоматически при старте контейнера `grafana` и сохраняются для всех пользователей инстанса (не нужно настраивать вручную в новой сессии).
- Список преднастроенных правил:
  1. `[Logs] Errors in any service > 0 (5m)` — критический уровень, срабатывает при любых error/fatal/exception логах.
  2. `[Logs] Warning burst in any service > 20 (10m)` — warning-уровень, всплеск предупреждений.
  3. `[Logs] Error spike in any service > 15 (5m)` — критический уровень, резкий рост ошибок.

Проверка, что правила загружены:
```bash
docker compose restart grafana
docker compose logs --tail=200 grafana
```

---

## 8. Операционные процедуры

## 8.1. Обновление корпуса A
1. Загрузить/заменить файлы в `data/inbox/csv_ans_docs`.
2. Выполнить: `docker compose run --rm ingest-a`.

## 8.2. Обновление корпуса B
1. Загрузить/заменить файлы в `data/inbox/internal_regulations`.
2. Выполнить: `docker compose run --rm ingest-b`.

> Перед запуском индексации следуйте чеклисту подготовки в [`docs/operations.md`](operations.md#подготовка-документов-к-индексации).

## 8.3. Бэкап
```bash
./scripts/backup_all.sh --mode offline
```

## 8.4. Восстановление
```bash
./scripts/restore_all.sh --mode offline data/backups/<timestamp>
```

---

## 9. Диагностика проблем

1. Нет GPU в контейнере:
   - перепроверьте шаги раздела 3;
   - проверьте `docker run --rm --gpus all ... nvidia-smi`;
   - убедитесь, что в `docker-compose.yml` для `llm-server` присутствует `gpus: all` (а не только `deploy.resources...`).

2. Нет ответов от LLM:
```bash
curl http://localhost:8080/health
```

3. Пустой retrieval:
- проверьте, что ingestion завершился без ошибок;
- проверьте наличие коллекций в Qdrant.

4. Нет логов в Grafana/Loki:
- проверьте `promtail` и `loki` логи;
- проверьте datasource Loki в Grafana.

---

## 10. Критерии готовности (Go-Live)
- [ ] GPU доступен в WSL2 и Docker.
- [ ] Все сервисы `docker compose ps` в состоянии `healthy/up`.
- [ ] Индексация A и B выполняется без ошибок.
- [ ] `/ask` возвращает ответ + источники.
- [ ] Логи видны в Loki/Grafana.
- [ ] Выполнены тестовые backup/restore.
