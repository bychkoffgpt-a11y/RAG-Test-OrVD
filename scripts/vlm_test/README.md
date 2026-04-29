# VLM test toolkit for `/ask` and `/v1/chat/completions`

Набор скриптов для **полной диагностики распознавания изображений** и локализации обрыва пути `images -> VLM`.

## Что внутри

- `vlm_test_cases.json` / `vlm_test_cases.csv` — 12 фиксированных тест-кейсов (URL + golden/negative facts).
- `run_vlm_ask.py` — прогоны кейсов через `/ask`.
- `run_vlm_chat_completions.py` — прогоны кейсов через `/v1/chat/completions`.
- `score_vlm_results.py` — базовая оценка (recall/hallucination/latency).
- `score_vlm_results_v2.py` — улучшенная оценка:
  - aliases/синонимы;
  - partial-credit по фактам;
  - метрики по группам (`text/chart/sign`).
- `probe_ask_vlm.py` — быстрый smoke probe `/ask` на одном изображении.
- `check_ask_trace.py` — проверка полноты диагностических этапов по `trace_id` в логах.
- `summarize_vlm_diagnostics.py` — сводный markdown-отчёт сравнения `/ask` vs `/chat`.
- `run_full_diagnostics.sh` — единый сценарий, который запускает всё end-to-end.

## Предварительные условия

1. Поднят `support-api` и доступен по `http://localhost:8000`.
2. Для runtime включён `VISION_RUNTIME_MODE=vlm` (иначе тестируете не VLM).
3. Из корня репозитория доступен Python 3.

Проверка API:
```bash
curl -sS http://localhost:8000/health
```

## Быстрый старт (одной командой)

```bash
cd scripts/vlm_test
bash ./run_full_diagnostics.sh
```

Артефакты будут в каталоге `scripts/vlm_test/out/<UTC timestamp>/`:
- JSONL ответы от `/ask` и `/chat`;
- базовые и v2 отчёты (JSON + CSV);
- `comparison.md` — итоговое сравнение.

## Параметры полного прогона

```bash
API_URL=http://localhost:8000 \
MODEL=local-vlm \
HIT_THRESHOLD=0.6 \
OUT_DIR=./out/manual_run \
bash ./run_full_diagnostics.sh
```

Переменные:
- `API_URL` — URL сервиса.
- `MODEL` — модель для `/v1/chat/completions`.
- `CASES_FILE` — путь к JSON с кейсами.
- `OUT_DIR` — каталог результатов.
- `HIT_THRESHOLD` — порог hard-hit для scorer v2.

## Пошаговый запуск вручную

```bash
cd scripts/vlm_test

# 1) Прогоны endpoint'ов
python3 run_vlm_ask.py --api-url http://localhost:8000 \
  --cases vlm_test_cases.json --out vlm_ask_results.jsonl

python3 run_vlm_chat_completions.py --api-url http://localhost:8000 \
  --model local-vlm --cases vlm_test_cases.json --out vlm_chat_results.jsonl

# 2) Scoring
python3 score_vlm_results.py --input vlm_ask_results.jsonl \
  --out-json vlm_ask_score_summary.json --out-csv vlm_ask_score_per_case.csv

python3 score_vlm_results_v2.py --input vlm_ask_results.jsonl \
  --out-json vlm_ask_score_v2_summary.json --out-csv vlm_ask_score_v2_per_case.csv

python3 score_vlm_results_v2.py --input vlm_chat_results.jsonl \
  --out-json vlm_chat_score_v2_summary.json --out-csv vlm_chat_score_v2_per_case.csv

# 3) Сводное сравнение
python3 summarize_vlm_diagnostics.py \
  --ask-summary vlm_ask_score_v2_summary.json \
  --chat-summary vlm_chat_score_v2_summary.json \
  --out-markdown comparison.md
```

## Быстрый debug `/ask`

```bash
python3 probe_ask_vlm.py --api-url http://localhost:8000 \
  --image-url "https://dummyimage.com/800x500/ffffff/000000.png&text=STOP+SIGN" \
  --runs 3
```

Проверяйте в выводе:
- `status` (должен быть `200`);
- `answer_preview` (должны быть визуально релевантные факты);
- `visual_evidence_len` (обычно `>0` для корректного vision path);
- `images_len` и `raw_keys`.

## Проверка трассировки по логам

Скрипт ищет обязательные этапы:
- `ask.request_received`
- `ask.request_parsed`
- `ask.route_selected`
- `ask.vision_preprocess_done`
- `ask.vlm_called`
- `ask.response_ready`

Запуск:
```bash
python3 check_ask_trace.py --log-file /path/to/support-api.log
```

Интерпретация:
- `[BROKEN] ... missing=['ask.vlm_called']` → обрыв до вызова VLM.
- `[BROKEN] ... missing=['ask.vision_preprocess_done']` → проблема в pre-processing изображений.

## Интерпретация результатов scoring

### Ключевые метрики
- `golden_hard_recall` — строгие совпадения (выше = лучше).
- `golden_partial_recall` — частичные совпадения по якорям/алиасам (выше = лучше).
- `hallucination_hard_rate` — доля совпадений с negative facts (ниже = лучше).
- `hallucination_partial_rate` — «мягкая» версия галлюцинаций (ниже = лучше).
- `latency_p50/p95` — медиана и хвост задержек.

### Практические паттерны
1. `/ask` почти 0, `/chat` заметно выше
   - вероятный обрыв image path именно в `/ask`.
2. recall растёт только при снижении `--hit-threshold`, но hall резко растёт
   - модель даёт шумные/нестабильные соответствия.
3. высокое `p95` только у `/chat`
   - тяжёлая VLM-инференс нагрузка/повторные попытки в этом endpoint.

## Сценарий «полная диагностика»

1. Прогнать `run_full_diagnostics.sh`.
2. Сверить `comparison.md`.
3. Если `/ask` сильно хуже `/chat`, сделать `probe_ask_vlm.py` на 2-3 картинках.
4. Проверить `check_ask_trace.py` на логах за эти trace_id.
5. Локализовать первый отсутствующий этап и исправлять соответствующий модуль (`api -> rag -> vision`).

## Дополнительно

- Более мягкий порог strict-match:
```bash
python3 score_vlm_results_v2.py --input vlm_chat_results.jsonl --hit-threshold 0.5
```

- Пользовательские aliases:
```bash
python3 score_vlm_results_v2.py --input vlm_chat_results.jsonl --aliases my_aliases.json
```
