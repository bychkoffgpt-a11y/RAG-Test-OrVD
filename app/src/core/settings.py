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

    qdrant_timeout_sec: float = 15.0

    llm_connect_timeout_sec: float = 5.0
    llm_read_timeout_sec: float = 120.0
    llm_write_timeout_sec: float = 10.0
    llm_pool_timeout_sec: float = 5.0


settings = Settings()
