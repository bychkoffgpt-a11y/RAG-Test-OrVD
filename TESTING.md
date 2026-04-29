# TESTING.md

## Тестовые уровни в проекте

### Unit (`app/tests/unit`)
Проверяют изолированную логику:
- chunking;
- retriever/prompt_builder/orchestrator;
- API schemas;
- clients (llm/embeddings);
- vision service.

Запуск:
```bash
cd app
pip install -e .[dev]
pytest -q app/tests/unit
```

### Integration (`app/tests/integration`)
Проверяют контрактные и интеграционные сценарии:
- OpenAI-compatible endpoint;
- download/external sources сценарии.

Запуск:
```bash
cd app
pytest -q app/tests/integration
```

### Полный прогон с покрытием
```bash
cd app
pytest -q --cov=src --cov-report=term-missing
```

## Предпусковые проверки инфраструктуры
```bash
./scripts/preflight_check.sh --mode offline
```

Дополнительно:
- online режим: `./scripts/preflight_check.sh --mode online`
- без Docker-проверок: `./scripts/preflight_check.sh --mode offline --skip-docker`

## Регрессия мультимодальности
При поднятом локальном стеке:
```bash
python3 scripts/run_vision_regression.py --api-url http://localhost:8000
```

## Политика качества перед merge
- Все unit-тесты зелёные.
- Integration-тесты зелёные для изменений API/контрактов.
- Для retrieval/chunking/prompt изменений — обязательный регрессионный прогон релевантных тестов.

## Быстрый bootstrap Python-окружения и тестов

Для хостов с нестабильным доступом к `pypi.org` используйте подготовленные скрипты:

```bash
# создать .venv и установить зависимости из app/pyproject.toml (+ dev)
./scripts/setup_python_env.sh

# запустить полный тестовый набор
./scripts/run_pytest_suite.sh
```

Скрипт `setup_python_env.sh` поддерживает переменные из `.env`:
- `PIP_INDEX_URL` — основной индекс;
- `PIP_FALLBACK_INDEX_URL` — fallback-зеркало при ошибке основного;
- `PIP_EXTRA_INDEX_URL` — дополнительный индекс (например, для wheel'ов torch).

Примеры:
```bash
# пересоздать окружение
./scripts/setup_python_env.sh --recreate

# только unit-тесты
./scripts/run_pytest_suite.sh --unit

# только integration-тесты
./scripts/run_pytest_suite.sh --integration
```
