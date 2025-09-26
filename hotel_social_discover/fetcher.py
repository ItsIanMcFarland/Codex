"""Async fetching utilities."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
from tenacity import AsyncRetrying, RetryError, retry_if_exception_type, stop_after_attempt, wait_exponential

from .parser import is_js_heavy, looks_like_captcha

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional heavy dependency
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover
    async_playwright = None  # type: ignore


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: Optional[int]
    body: Optional[str]
    elapsed_ms: Optional[int]
    error: Optional[str] = None
    snapshot_path: Optional[str] = None


class Fetcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        timeout: float,
        render: bool,
        headful: bool,
        rate_limit_per_domain: float,
        user_agent: str,
        save_snapshots: bool = False,
        snapshot_dir: Optional[str] = None,
    ) -> None:
        self.client = client
        self.timeout = timeout
        self.render = render and async_playwright is not None
        self.headful = headful
        self.rate_limit_per_domain = rate_limit_per_domain
        self.user_agent = user_agent
        self.save_snapshots = save_snapshots
        self.snapshot_dir = snapshot_dir
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}

    async def _rate_limit(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.netloc
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._last_request.get(host, 0.0)
            delta = now - last
            if delta < self.rate_limit_per_domain:
                await asyncio.sleep(self.rate_limit_per_domain - delta)
            self._last_request[host] = time.monotonic()

    async def fetch(self, url: str, render_hint: bool = False, proxy: Optional[str] = None) -> FetchResult:
        await self._rate_limit(url)
        start = time.perf_counter()
        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=4),
                retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            ):
                with attempt:
                    response = await self.client.get(
                        url,
                        timeout=self.timeout,
                        proxies=proxy if proxy else None,
                    )
                    elapsed_ms = int((time.perf_counter() - start) * 1000)
                    body = response.text
                    if looks_like_captcha(body):
                        return FetchResult(
                            url=url,
                            final_url=str(response.url),
                            status_code=response.status_code,
                            body=body,
                            elapsed_ms=elapsed_ms,
                            error="captcha_detected",
                        )
                    need_render = self.render and (render_hint or is_js_heavy(body))
                    snapshot_path = None
                    if need_render:
                        rendered = await self.render_page(str(response.url))
                        if rendered:
                            body, snapshot_path = rendered
                    return FetchResult(
                        url=url,
                        final_url=str(response.url),
                        status_code=response.status_code,
                        body=body,
                        elapsed_ms=elapsed_ms,
                        snapshot_path=snapshot_path,
                    )
        except RetryError as exc:
            last_attempt = exc.last_attempt
            error_message = str(last_attempt.exception()) if last_attempt else str(exc)
            return FetchResult(url=url, final_url=url, status_code=None, body=None, elapsed_ms=None, error=error_message)
        except Exception as exc:
            return FetchResult(url=url, final_url=url, status_code=None, body=None, elapsed_ms=None, error=str(exc))

    async def render_page(self, url: str) -> Optional[tuple[str, Optional[str]]]:
        if async_playwright is None:
            logger.debug("Playwright not installed; skipping render")
            return None
        try:
            async with async_playwright() as p:  # pragma: no cover - heavy
                browser = await p.chromium.launch(headless=not self.headful)
                page = await browser.new_page(user_agent=self.user_agent)
                await page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
                content = await page.content()
                snapshot_path = None
                if self.save_snapshots and self.snapshot_dir:
                    Path = __import__("pathlib").Path  # lazy import
                    Path(self.snapshot_dir).mkdir(parents=True, exist_ok=True)
                    safe_name = urlparse(url).netloc.replace(":", "_")
                    snapshot_path = str(Path(self.snapshot_dir) / f"{safe_name}.png")
                    await page.screenshot(path=snapshot_path, full_page=True)
                await browser.close()
                return content, snapshot_path
        except Exception as exc:  # pragma: no cover - heavy
            logger.debug("Playwright rendering failed for %s: %s", url, exc)
            return None


__all__ = ["Fetcher", "FetchResult"]
