from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Store Intelligence API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Direct DATABASE_URL — used by Railway/Render/Heroku (overrides individual params)
    DATABASE_URL: Optional[str] = None

    # Individual PostgreSQL params — used for local / docker-compose
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "store_intelligence"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"

    # Connection pool tuning
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    @property
    def database_url(self) -> str:
        """
        Returns the database URL.
        Priority: DATABASE_URL env var (Railway/cloud) → individual POSTGRES_* params.
        Handles Railway's postgres:// prefix (SQLAlchemy needs postgresql://).
        """
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            # Railway / Heroku use postgres:// but SQLAlchemy requires postgresql://
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
