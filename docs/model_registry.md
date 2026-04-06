# Реестр моделей (обязательные артефакты)

> Этот документ фиксирует **конкретный стек моделей** для проекта.  
> Любое изменение модели/квантизации/пути должно сопровождаться обновлением этого файла и `.env.example`.

## 1) Какие модели используем

| Назначение | Зафиксированный артефакт | Локальный путь в проекте | Переменная/настройка |
|---|---|---|---|
| LLM (генерация) | `qwen2.5-7b-instruct-q4_k_m.gguf` | `models/llm/qwen2.5-7b-instruct-q4_k_m.gguf` | `LLM_MODEL_FILE` |
| Embeddings | `BAAI/bge-m3` | `models/embeddings/bge-m3/` | `embedding_model_path` |
| Reranker | `BAAI/bge-reranker-v2-m3` | `models/reranker/bge-reranker-v2-m3/` | `reranker_model_path` |

## 2) Политика версионирования

- Для LLM версия фиксируется именем GGUF-файла: `qwen2.5-7b-instruct-q4_k_m.gguf`.
- Для Embeddings и Reranker версия фиксируется парой:
  - upstream model id (`BAAI/bge-m3`, `BAAI/bge-reranker-v2-m3`);
  - контрольная сумма (SHA256) офлайн-архива/каталога, поставляемого в контур.

## 3) Что нужно положить в репозиторий перед запуском

```text
models/
  llm/
    qwen2.5-7b-instruct-q4_k_m.gguf
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

## 4) Проверка целостности (рекомендуется)

Заполните в `.env`:
- `LLM_MODEL_SHA256`
- `EMBEDDING_MODEL_SHA256`
- `RERANKER_MODEL_SHA256`

И затем проверьте контрольные суммы локально (пример для LLM):

```bash
sha256sum models/llm/qwen2.5-7b-instruct-q4_k_m.gguf
```

> Примечание: контрольные суммы должны приходить из вашего доверенного офлайн-источника артефактов (внутренний registry/архив поставки).
