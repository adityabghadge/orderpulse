from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables prefixed with ORDERPULSE_.

    Values can also come from a local `.env` file. Real environment variables win over `.env`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ORDERPULSE_", extra="ignore")

    app_name: str = "OrderPulse API"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://orderpulse:orderpulse@localhost:5433/orderpulse"
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
