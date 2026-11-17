from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./finai.db"
    jwt_secret: str = "dev-only-change-me"
    jwt_expire_hours: int = 24
    cookie_secure: bool = False
    cors_origin: str = "http://localhost:5173"
    llm_provider: str = "mock"  # openai | mock
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_s: int = 15
    daily_llm_rows_limit: int = 200
    max_upload_bytes: int = 2 * 1024 * 1024


settings = Settings()
