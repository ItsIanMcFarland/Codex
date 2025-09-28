"""Configuration management for the social discovery service."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Application settings using environment variables."""

    # Core service
    environment: str = Field("development", description="Deployment environment name")
    log_level: str = Field("INFO", description="Python logging level")
    data_dir: Path = Field(Path("./data"), description="Directory to store checkpoints and artifacts")

    # Database
    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/social_discovery",
        description="SQLAlchemy compatible DSN",
    )
    alembic_ini_path: Path = Field(Path("./alembic.ini"), description="Path to alembic.ini for migrations")

    # Redis / broker for distributed queues
    redis_url: str = Field("redis://localhost:6379/0", description="Redis connection URI")

    # Proxy configuration
    proxy_list_path: Optional[Path] = Field(
        None, description="Path to newline separated proxies in schema://user:pass@host:port format"
    )
    proxy_rotation_seconds: int = Field(300, ge=1, description="How frequently proxies should be rotated")
    proxy_failure_threshold: int = Field(5, ge=1, description="Failures before a proxy is quarantined")
    proxy_quarantine_seconds: int = Field(900, ge=60, description="Quarantine duration for unhealthy proxies")

    # Rate limiting & politeness
    per_domain_concurrency: int = Field(2, ge=1, description="Max concurrent tasks per domain")
    per_domain_delay_seconds: float = Field(1.5, ge=0.0, description="Delay between requests to same domain")
    global_rate_limit_per_minute: int = Field(600, ge=1, description="Global rate limit for fetch attempts")

    # Retry configuration
    max_retries: int = Field(3, ge=0, description="Maximum retries for a fetch job")
    request_timeout_seconds: int = Field(20, ge=1, description="HTTP request timeout")

    # Security
    admin_api_keys: List[str] = Field(default_factory=list, description="Admin level API keys")
    submitter_api_keys: List[str] = Field(default_factory=list, description="Submitter level API keys")

    # Monitoring
    enable_metrics: bool = Field(True, description="Whether to expose Prometheus metrics")
    metrics_port: int = Field(9000, description="Port for Prometheus metrics server")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @validator("admin_api_keys", "submitter_api_keys", pre=True)
    def _split_api_keys(cls, value: Optional[str]):  # type: ignore[override]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value or []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


__all__ = ["Settings", "get_settings"]
