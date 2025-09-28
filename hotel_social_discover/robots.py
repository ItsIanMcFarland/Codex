"""Robots.txt fetching and compliance."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

import httpx

try:  # pragma: no cover - optional dependency
    from robotexclusionrulesparser import RobotExclusionRulesParser as RobotsParser
except Exception:  # pragma: no cover
    from urllib import robotparser as _robotparser

    class RobotsParser:  # type: ignore
        def __init__(self) -> None:
            self._parser = _robotparser.RobotFileParser()

        def set_url(self, url: str) -> None:
            self._parser.set_url(url)

        def read(self) -> None:
            self._parser.read()

        def can_fetch(self, useragent: str, url: str) -> bool:
            return self._parser.can_fetch(useragent, url)

        def parse(self, content: str) -> None:
            self._parser.parse(content.splitlines())


logger = logging.getLogger(__name__)


@dataclass
class RobotsCacheEntry:
    parser: RobotsParser
    fetched: bool


class RobotsManager:
    """Manage robots.txt fetching and caching."""

    def __init__(self, user_agent: str, client: httpx.AsyncClient) -> None:
        self.user_agent = user_agent
        self.client = client
        self._lock = asyncio.Lock()
        self._cache: Dict[str, RobotsCacheEntry] = {}

    async def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        async with self._lock:
            entry = self._cache.get(base)
            if entry is None:
                entry = RobotsCacheEntry(parser=RobotsParser(), fetched=False)
                self._cache[base] = entry

        if not entry.fetched:
            robots_url = urljoin(base, "/robots.txt")
            try:
                response = await self.client.get(robots_url, timeout=10.0)
                response.raise_for_status()
                entry.parser.parse(response.text)
                logger.debug("Fetched robots.txt from %s", robots_url)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.debug("Failed to fetch robots.txt from %s: %s", robots_url, exc)
            finally:
                entry.fetched = True

        try:
            allowed = entry.parser.can_fetch(self.user_agent, url)
        except Exception:
            allowed = True
        return allowed if allowed is not None else True


__all__ = ["RobotsManager"]
