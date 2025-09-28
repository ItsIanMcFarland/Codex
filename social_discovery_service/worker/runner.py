"""Async worker runner for fetching social links."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
import httpx
from playwright.async_api import async_playwright

from ..config import Settings
from ..jobs.checkpoint import CheckpointStore
from ..jobs.manager import JobManager
from ..monitoring.metrics import WORKER_ERRORS, WORKER_JOBS_COMPLETED, WORKER_JOBS_FAILED
from .proxy import get_proxy_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def playwright_browser():
    playwright = await async_playwright().start()
    browser = await playwright.firefox.launch(headless=True)
    try:
        yield browser
    finally:
        await browser.close()
        await playwright.stop()


async def run_worker(manager: JobManager, queue: str, once: bool, settings: Settings) -> None:
    proxy_pool = get_proxy_pool()
    checkpoint = CheckpointStore()

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        async with playwright_browser() as browser:
            while True:
                job = await manager.reserve_next_job(queue)
                if job is None:
                    if once:
                        break
                    await asyncio.sleep(1)
                    continue

                proxy = await proxy_pool.get_proxy()
                logger.info("Processing job", extra={"job_id": job.job_id, "domain": job.domain, "proxy": proxy})
                checkpoint.update_job(queue, job.job_id)

                try:
                    result = await manager.process_job(job, client=client, browser=browser, proxy=proxy)
                except Exception as exc:  # pragma: no cover - worker level guard
                    logger.exception("Job failed", extra={"job_id": job.job_id})
                    WORKER_ERRORS.inc()
                    await proxy_pool.record_failure(proxy)
                    await manager.mark_job_failed(job, str(exc))
                else:
                    if result:
                        WORKER_JOBS_COMPLETED.inc()
                        await proxy_pool.record_success(proxy)
                        await manager.mark_job_completed(job, result)
                    else:
                        WORKER_JOBS_FAILED.inc()
                        await proxy_pool.record_failure(proxy)
                        await manager.mark_job_failed(job, "No links discovered")

                checkpoint.clear_job(queue)

                if once:
                    break
