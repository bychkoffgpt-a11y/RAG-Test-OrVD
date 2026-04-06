# Офлайн RAG-платформа первой линии поддержки ЦСВ АНС

Репозиторий содержит полностью локальный стек (без интернета и облаков) для запуска чат-бота поддержки на базе документации ЦСВ АНС и внутренних нормативных документов.

## Состав решения
- Open WebUI (чат-интерфейс)
- FastAPI (кастомный backend)
- Qdrant (векторный поиск)
- llama.cpp server (локальная LLM)
- PostgreSQL (метаданные)
- Prometheus + Grafana (метрики)
- Loki + Promtail (централизованные логи)

## Быстрый старт
```bash
cp .env.example .env
./scripts/bootstrap_offline.sh
docker compose up -d
```

## Документация
- [Архитектура](docs/architecture.md)
- [Развёртывание в WSL2 (подробно)](docs/deployment_wsl2.md)
- [Эксплуатация](docs/operations.md)
