"""集中配置：全部来自环境变量，默认值与 .env.example 保持一致。"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "rentlens"
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "rentlens"
    db_user: str = "rentlens"
    db_password: str = "rentlens_pw_2026"

    jwt_secret: str = "rentlens-jwt-secret-change-me-2026"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480

    redis_url: str = "redis://localhost:6379/0"
    seed_demo: bool = True
    rate_limit_per_minute: int = 300
    rate_limit_write_per_minute: int = 60
    app_timezone_offset_minutes: int = 480
    crawl_backoff_base_ms: int = 800
    fixture_dir: str = "fixtures"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
