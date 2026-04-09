from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_env: str = 'dev'
    app_name: str = 'CSV ANS Support API'
    log_level: str = 'INFO'

    postgres_dsn: str = 'postgresql://support_user:change_me_strong@localhost:5432/support'
    qdrant_url: str = 'http://localhost:6333'
    llm_base_url: str = 'http://localhost:8080'
    file_storage_root: str = '/data'
    loki_url: str = 'http://localhost:3100'

    embedding_model_path: str = '/models/embeddings/bge-m3'
    reranker_model_path: str = '/models/reranker/bge-reranker-v2-m3'
    embedding_device: str = 'auto'
    reranker_device: str = 'auto'
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
