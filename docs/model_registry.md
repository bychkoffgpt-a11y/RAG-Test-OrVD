# Реестр моделей (обязательные артефакты)

> Этот документ фиксирует **конкретный стек моделей** для проекта.  
> Любое изменение модели/квантизации/пути должно сопровождаться обновлением этого файла и `.env.example`.

## 1) Какие модели используем

| Назначение | Зафиксированный артефакт | Локальный путь в проекте | Переменная/настройка |
|---|---|---|---|
| LLM (генерация) | `qwen2.5-7b-instruct-q4_k_m.gguf` | `models/llm/qwen2.5-7b-instruct-q4_k_m.gguf` | `LLM_MODEL_FILE` |
| Vision (VLM-распознавание) | `Qwen/Qwen3-VL-2B-Instruct` | `models/vision/qwen3-vl-2b-instruct/` | `VISION_MODEL_PATH` |
| OCR (распознавание текста на изображениях) | `PaddleOCR PP-OCRv4` (`det/rec/cls`) | `models/ocr/{det,rec,cls}/` | `VISION_OCR_MODEL_ROOT` |
| Embeddings | `BAAI/bge-m3` | `models/embeddings/bge-m3/` | `EMBEDDING_MODEL_PATH` / `embedding_model_path` |
| Reranker | `BAAI/bge-reranker-v2-m3` | `models/reranker/bge-reranker-v2-m3/` | `RERANKER_MODEL_PATH` / `reranker_model_path` |

## 2) Политика версионирования

- Для LLM версия фиксируется именем GGUF-файла: `qwen2.5-7b-instruct-q4_k_m.gguf`.
- Для Vision/Embeddings/Reranker версия фиксируется upstream model id и неизменностью локальных каталогов в `models/`.
- Для OCR версия фиксируется набором трёх inference-компонентов (`det/rec/cls`) и их контрольными суммами из доверенного источника поставки.

## 3) Целевая структура `models/`

```text
models/
  llm/
    qwen2.5-7b-instruct-q4_k_m.gguf
  vision/
    qwen3-vl-2b-instruct/
      config.json
      processor_config.json
      ...
  ocr/
    det/
      inference.pdmodel
      inference.pdiparams
    rec/
      inference.pdmodel
      inference.pdiparams
    cls/
      inference.pdmodel
      inference.pdiparams
  embeddings/
    bge-m3/
      config.json
      tokenizer.json
      ...
  reranker/
    bge-reranker-v2-m3/
      config.json
      tokenizer.json
      ...
```

> Важно: `scripts/preflight_check.sh` проверяет, что OCR-файлы лежат **непосредственно** в `det/`, `rec/`, `cls/` (без вложенных `*_infer/` директорий).

## 4) Готовые ссылки и команды для онлайн-загрузки

> Для production/offline-контуров используйте внутренний артефактный registry. Команды ниже нужны для первичной подготовки артефактов в online-среде.

### 4.1 Через готовый скрипт (рекомендуется)

```bash
./scripts/download_models_online.sh
```

Скрипт:
- скачивает Vision/Embeddings/Reranker через `huggingface-cli`;
- скачивает OCR-модели PaddleOCR (`det/rec/cls`) по прямым ссылкам;
- приводит структуру OCR к виду, который ожидает `preflight_check.sh`.

### 4.2 Ручной вариант (если нужен пошаговый контроль)

```bash
# 1) Hugging Face модели
huggingface-cli download Qwen/Qwen3-VL-2B-Instruct \
  --local-dir ./models/vision/qwen3-vl-2b-instruct

huggingface-cli download BAAI/bge-m3 \
  --local-dir ./models/embeddings/bge-m3

huggingface-cli download BAAI/bge-reranker-v2-m3 \
  --local-dir ./models/reranker/bge-reranker-v2-m3

# 2) PaddleOCR det/rec/cls
mkdir -p ./models/ocr/{det,rec,cls} /tmp/paddle_ocr_dl
curl -fL https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar -o /tmp/paddle_ocr_dl/det.tar
curl -fL https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar -o /tmp/paddle_ocr_dl/rec.tar
curl -fL https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar -o /tmp/paddle_ocr_dl/cls.tar

tar -xf /tmp/paddle_ocr_dl/det.tar -C /tmp/paddle_ocr_dl
tar -xf /tmp/paddle_ocr_dl/rec.tar -C /tmp/paddle_ocr_dl
tar -xf /tmp/paddle_ocr_dl/cls.tar -C /tmp/paddle_ocr_dl

cp /tmp/paddle_ocr_dl/ch_PP-OCRv4_det_infer/inference.pdmodel ./models/ocr/det/
cp /tmp/paddle_ocr_dl/ch_PP-OCRv4_det_infer/inference.pdiparams ./models/ocr/det/
cp /tmp/paddle_ocr_dl/ch_PP-OCRv4_rec_infer/inference.pdmodel ./models/ocr/rec/
cp /tmp/paddle_ocr_dl/ch_PP-OCRv4_rec_infer/inference.pdiparams ./models/ocr/rec/
cp /tmp/paddle_ocr_dl/ch_ppocr_mobile_v2.0_cls_infer/inference.pdmodel ./models/ocr/cls/
cp /tmp/paddle_ocr_dl/ch_ppocr_mobile_v2.0_cls_infer/inference.pdiparams ./models/ocr/cls/
```

## 5) Проверка целостности и готовности

```bash
# Контрольные суммы (пример)
sha256sum models/llm/qwen2.5-7b-instruct-q4_k_m.gguf

# Обязательные файлы
./scripts/preflight_check.sh --mode offline --check-ocr-stack
```

> Примечание: эталонные SHA256 должны приходить из вашего доверенного офлайн-источника артефактов (внутренний registry/архив поставки).
