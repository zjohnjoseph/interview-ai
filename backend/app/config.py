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


settings = Settings()