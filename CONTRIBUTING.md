# CONTRIBUTING.md

## Цель
Единые правила для безопасных изменений в offline RAG-платформе.

## Локальный setup
1. Проверить Docker:
   - `docker --version`
   - `docker compose version`
2. Создать `.env`:
   - `cp .env.example .env`
3. Выполнить preflight:
   - `./scripts/preflight_check.sh --mode offline`

## Ветки и коммиты
- Ветки: `feature/<name>`, `fix/<name>`, `docs/<name>`.
- Коммиты: conventional style (`feat`, `fix`, `refactor`, `test`, `docs`, `chore`).

Примеры:
- `feat(retrieval): tune min score threshold`
- `docs(architecture): document ingestion flow`

## Обязательные проверки перед PR
- Для Python-кода:
  - `cd app && pip install -e .[dev]`
  - `cd app && pytest -q --cov=src --cov-report=term-missing`
- Для изменённых shell-скриптов:
  - `bash -n <script_path>`
- Для мультимодальных изменений (при поднятом стеке):
  - `python3 scripts/run_vision_regression.py --api-url http://localhost:8000`

## PR checklist
- [ ] Описана проблема и мотивация.
- [ ] Описано решение и затронутые модули.
- [ ] Указаны выполненные проверки и их результат.
- [ ] Обновлены релевантные docs (`ARCHITECTURE.md`, `API_CONTRACTS.md`, `PROMPTS.md`, `TESTING.md`).
- [ ] Для API-изменений обновлены integration-тесты.
- [ ] Для retrieval/chunking/reranker-изменений обновлены unit-тесты.

## Ограничения
- Не добавлять новые зависимости без оценки влияния на offline wheelhouse.
- Не менять формат `sources/images/visual_evidence` без версии API и миграционного плана.
- Не коммитить секреты, токены и персональные данные.
