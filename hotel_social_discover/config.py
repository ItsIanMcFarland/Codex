"""Configuration utilities for Hotel Social Discover."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


@dataclass
class Config:
    """Runtime configuration parameters."""

    concurrency: int = 10
    timeout: float = 12.0
    render: bool = False
    headful: bool = False
    rate_limit_per_domain: float = 2.0
    user_agent: str = "hotel-social-discover/0.1"
    checkpoint_path: Path = Path(".hotel_social_discover_checkpoint.json")
    summary_json: Path = Path("results.summary.json")
    proxy_list: Optional[List[str]] = None


def parse_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def load_config(env_file: Optional[str] = ".env") -> Config:
    """Load configuration from environment variables and optional .env file."""

    if env_file:
        load_dotenv(env_file, override=False)

    config = Config(
        concurrency=int(os.getenv("HSD_CONCURRENCY", Config.concurrency)),
        timeout=float(os.getenv("HSD_TIMEOUT", Config.timeout)),
        render=parse_bool(os.getenv("HSD_RENDER", str(Config.render)).lower()),
        headful=parse_bool(os.getenv("HSD_HEADFUL", str(Config.headful)).lower()),
        rate_limit_per_domain=float(
            os.getenv("HSD_RATE_LIMIT_PER_DOMAIN", Config.rate_limit_per_domain)
        ),
        user_agent=os.getenv("HSD_USER_AGENT", Config.user_agent),
        checkpoint_path=Path(
            os.getenv("HSD_CHECKPOINT_PATH", str(Config.checkpoint_path))
        ),
        summary_json=Path(os.getenv("HSD_SUMMARY_JSON", str(Config.summary_json))),
    )

    proxy_file = os.getenv("HSD_PROXY_FILE")
    if proxy_file and Path(proxy_file).exists():
        proxies = Path(proxy_file).read_text().splitlines()
        config.proxy_list = [p.strip() for p in proxies if p.strip()]

    return config


__all__ = ["Config", "load_config", "parse_bool"]
