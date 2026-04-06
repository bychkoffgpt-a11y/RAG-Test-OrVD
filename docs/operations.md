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

## Бэкап
1. Экспорт БД и файлов: `./scripts/backup_all.sh`
2. Восстановление: `./scripts/restore_all.sh data/backups/<timestamp>`
