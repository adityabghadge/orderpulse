from functools import lru_cache
from pathlib import Path

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

    redis_url: str = "redis://localhost:6380/0"
    # How long the dashboard overview may be served from cache (writes clear it immediately).
    overview_cache_seconds: int = 30
    # How often the API refreshes the precomputed daily totals in the background.
    stats_refresh_seconds: int = 300
    background_jobs: bool = True

    # Where trained models are saved and loaded from.
    model_dir: Path = Path(__file__).resolve().parents[2] / "artifacts"
    # Below this confidence the routing model defers to the customer's dropdown choice.
    routing_min_confidence: float = 0.6


@lru_cache
def get_settings() -> Settings:
    return Settings()
