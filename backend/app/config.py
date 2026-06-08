from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Database
    database_url: str
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_db: str = ""

    # Redis
    redis_url: str = "redis://redis:6379"

    # JWT Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 1440

    # LLM APIs
    groq_api_key: str = ""
    gemini_api_key: str = ""
    jina_api_key: str = ""
    jina_embedding_model: str = "jina-embeddings-v3"
    jina_reranker_model: str = "jina-reranker-v2-base-multilingual"
    embedding_dimension: int = 768

    # LLM model settings
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.0-flash"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024


settings = Settings()