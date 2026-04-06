# Эксплуатация

## Базовые команды
- Запуск: `docker compose up -d`
- Остановка: `docker compose down`
- Статус: `docker compose ps`
- Логи API: `docker compose logs -f support-api`

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
