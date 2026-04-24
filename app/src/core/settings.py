from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_env: str = 'dev'
    app_name: str = 'CSV ANS Support API'
    log_level: str = 'INFO'
    suppress_metrics_request_logs: bool = True
    suppress_metrics_access_logs: bool = True

    postgres_dsn: str = 'postgresql://support_user:change_me_strong@localhost:5432/support'
    qdrant_url: str = 'http://localhost:6333'
    llm_base_url: str = 'http://localhost:8080'
    file_storage_root: str = '/data'
    loki_url: str = 'http://localhost:3100'

    embedding_model_path: str = '/models/embeddings/bge-m3'
    reranker_model_path: str = '/models/reranker/bge-reranker-v2-m3'
    embedding_device: str = 'auto'
    embedding_device_strict: bool = False
    reranker_device: str = 'auto'

    vision_enabled: bool = True
    vision_ingest_enabled: bool = True
    vision_runtime_mode: str = 'ocr'
    vision_ingest_mode: str = 'ocr'
    vision_ocr_model_root: str = '/models/ocr'
    vision_ocr_lang: str = 'ru'
    vision_ocr_device: str = 'auto'
    vision_ocr_use_angle_cls: bool = True
    vision_ocr_show_log: bool = False
    vision_model_path: str = '/models/vision/qwen3-vl-2b-instruct'
    vision_model_device: str = 'auto'
    vision_model_dtype: str = 'auto'
    vision_model_max_new_tokens: int = 160
    vision_runtime_timeout_sec: float = 120.0
    vision_runtime_max_images: int = 3
    vision_runtime_max_image_pixels: int = 4_194_304
    vision_runtime_preload: bool = True
    vision_attachment_max_bytes: int = 10 * 1024 * 1024
    vision_attachment_allowed_mime_types: set[str] = {
        'image/png',
        'image/jpeg',
        'image/webp',
        'image/bmp',
        'image/tiff',
        'image/gif',
    }
    vision_attachment_path_aliases: str = '/app/backend/data/uploads=/data/runtime_uploads'
    vision_model_prompt_runtime: str = (
        'Опиши скриншот пользователя для службы поддержки. '
        'Если видны ошибки/коды/статусы — укажи их.'
    )
    vision_model_prompt_ingest: str = (
        'Кратко опиши изображение для индексации документации. '
        'Укажи важные надписи, элементы интерфейса и возможные коды ошибок.'
    )
    chunk_size_csv_ans_docs: int = 1100
    chunk_overlap_csv_ans_docs: int = 150
    chunk_strategy_csv_ans_docs: str = 'docs'
    chunk_size_internal_regulations: int = 700
    chunk_overlap_internal_regulations: int = 160
    chunk_strategy_internal_regulations: str = 'regs'

    qdrant_timeout_sec: float = 15.0

    retrieval_candidate_pool_multiplier: int = 3
    retrieval_min_score: float = 0.25
    retrieval_use_reranker: bool = True

    llm_connect_timeout_sec: float = 5.0
    llm_read_timeout_sec: float = 120.0
    llm_write_timeout_sec: float = 10.0
    llm_pool_timeout_sec: float = 5.0


settings = Settings()
