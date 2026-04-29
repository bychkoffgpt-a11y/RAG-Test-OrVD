# VLM test toolkit for `/ask` and `/v1/chat/completions`

Набор скриптов для диагностики качества распознавания картинок и локализации обрыва пути `images -> VLM`.

## Что внутри

- `vlm_test_cases.json` / `vlm_test_cases.csv` — 12 тест-кейсов (URL + golden/negative facts).
- `run_vlm_ask.py` — прогоны кейсов через `/ask`.
- `run_vlm_chat_completions.py` — прогоны кейсов через `/v1/chat/completions`.
- `score_vlm_results.py` — базовый scorer.
- `score_vlm_results_v2.py` — scorer v2 (aliases + partial-credit + group metrics).
- `probe_ask_vlm.py` — быстрый probe `/ask` на одном изображении.
- `check_ask_trace.py` — проверка наличия диагностических этапов в логах по `trace_id`.

## Быстрый старт

```bash
cd scripts/vlm_test

python3 run_vlm_ask.py --api-url http://localhost:8000 \
  --cases vlm_test_cases.json --out vlm_ask_results.jsonl

python3 run_vlm_chat_completions.py --api-url http://localhost:8000 \
  --model local-vlm --cases vlm_test_cases.json --out vlm_chat_results.jsonl

python3 score_vlm_results_v2.py --input vlm_ask_results.jsonl \
  --out-json vlm_ask_score_v2_summary.json --out-csv vlm_ask_score_v2_per_case.csv

python3 score_vlm_results_v2.py --input vlm_chat_results.jsonl \
  --out-json vlm_chat_score_v2_summary.json --out-csv vlm_chat_score_v2_per_case.csv
```

## Чеклист отладки `/ask`

1. Убедиться, что `/ask` получает `images`:
   - `probe_ask_vlm.py` должен показывать адекватные `images_len`/`visual_evidence_len`.
2. Сопоставить `/ask` и `/v1/chat/completions` на одном и том же кейсе.
3. Проверить трассировку этапов в логах:
   - `ask.request_received`
   - `ask.request_parsed`
   - `ask.route_selected`
   - `ask.vision_preprocess_done`
   - `ask.vlm_called`
   - `ask.response_ready`
4. Запустить `check_ask_trace.py` и выявить отсутствующий этап.

Пример:
```bash
python3 probe_ask_vlm.py --api-url http://localhost:8000 \
  --image-url "https://dummyimage.com/800x500/ffffff/000000.png&text=STOP+SIGN" --runs 3

python3 check_ask_trace.py --log-file /path/to/support-api.log
```

## Интерпретация симптомов

- `images_count=0` уже в request parse: mismatch схемы запроса.
- route=`text_only` при `images>0`: ошибка routing/feature flag.
- route=`vlm`, но нет `vlm_called`: обрыв вызова model adapter.
- `vlm_called=true`, но `visual_evidence` пусто: ошибка post-processing/response mapping.

## Примечания

- Для более мягкого hard-hit порога:
```bash
python3 score_vlm_results_v2.py --input vlm_chat_results.jsonl --hit-threshold 0.5
```
- Пользовательские алиасы можно добавить через JSON:
```bash
python3 score_vlm_results_v2.py --input vlm_chat_results.jsonl --aliases my_aliases.json
```
