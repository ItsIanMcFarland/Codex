"""Proxy rotation and health tracking."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..config import get_settings


@dataclass
class ProxyState:
    proxy_url: str
    failures: int = 0
    quarantined_until: Optional[float] = None

    def is_available(self) -> bool:
        if self.quarantined_until is None:
            return True
        return self.quarantined_until <= asyncio.get_event_loop().time()


@dataclass
class ProxyPool:
    proxies: Dict[str, ProxyState] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def load_from_file(self, path: Path) -> int:
        lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
        for line in lines:
            self.proxies.setdefault(line, ProxyState(proxy_url=line))
        return len(lines)

    async def get_proxy(self) -> Optional[str]:
        async with self.lock:
            available = [p for p in self.proxies.values() if p.is_available()]
            if not available:
                return None
            choice = random.choice(available)
            return choice.proxy_url

    async def record_failure(self, proxy_url: Optional[str]) -> None:
        if not proxy_url:
            return
        settings = get_settings()
        async with self.lock:
            state = self.proxies.setdefault(proxy_url, ProxyState(proxy_url=proxy_url))
            state.failures += 1
            if state.failures >= settings.proxy_failure_threshold:
                state.quarantined_until = asyncio.get_event_loop().time() + settings.proxy_quarantine_seconds

    async def record_success(self, proxy_url: Optional[str]) -> None:
        if not proxy_url:
            return
        async with self.lock:
            state = self.proxies.setdefault(proxy_url, ProxyState(proxy_url=proxy_url))
            state.failures = 0
            state.quarantined_until = None


_global_pool: Optional[ProxyPool] = None


def get_proxy_pool() -> ProxyPool:
    global _global_pool
    if _global_pool is None:
        pool = ProxyPool()
        settings = get_settings()
        if settings.proxy_list_path and settings.proxy_list_path.exists():
            pool.load_from_file(settings.proxy_list_path)
        _global_pool = pool
    return _global_pool


__all__ = ["ProxyPool", "ProxyState", "get_proxy_pool"]
