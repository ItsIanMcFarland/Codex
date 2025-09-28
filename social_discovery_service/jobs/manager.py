"""Job management and processing logic."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import httpx
from playwright.async_api import Browser
from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload

from hotel_social_discover.parser import is_js_heavy, looks_like_captcha, parse_social_links

from ..config import get_settings
from ..db.models import CrawlJob as CrawlJobModel
from ..db.models import DiscoveredLink as DiscoveredLinkModel
from ..db.models import FetchAttempt as FetchAttemptModel
from ..db.models import Hotel as HotelModel
from ..db.session import session_scope
from ..monitoring.metrics import (
    FETCH_ATTEMPTS_TOTAL,
    FETCH_LATENCY,
    IN_PROGRESS_JOBS,
    LINKS_DISCOVERED_TOTAL,
)
from ..worker.proxy import ProxyPool, get_proxy_pool
from .models import CrawlJob, JobBatch

logger = logging.getLogger(__name__)


class JobManager:
    """Coordinates queueing, fetching, and persisting job results."""

    def __init__(self, proxy_pool: Optional[ProxyPool] = None) -> None:
        self.settings = get_settings()
        self.proxy_pool = proxy_pool or get_proxy_pool()
        self._domain_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._domain_last_request: Dict[str, float] = defaultdict(lambda: 0.0)
        self._domain_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self.settings.per_domain_concurrency)
        )

    async def enqueue_batch(self, batch_name: str, domains: List[str], metadata: Dict) -> JobBatch:
        batch = JobBatch.create(batch_name, domains, metadata)
        async with session_scope() as session:
            for job in batch.jobs:
                domain = job.domain.lower().strip()
                hotel = await session.scalar(select(HotelModel).where(HotelModel.domain == domain))
                if not hotel:
                    hotel = HotelModel(domain=domain)
                    session.add(hotel)
                    await session.flush()

                db_job = CrawlJobModel(job_id=job.job_id, hotel_id=hotel.id, metadata=job.metadata)
                session.add(db_job)
                await session.flush()
                job.db_id = db_job.id
        logger.info("Enqueued batch", extra={"batch_name": batch_name, "job_count": len(batch.jobs)})
        return batch

    async def get_job(self, job_id: str) -> Optional[CrawlJob]:
        async with session_scope() as session:
            db_job = await session.scalar(
                select(CrawlJobModel)
                .options(joinedload(CrawlJobModel.hotel))
                .where(CrawlJobModel.job_id == job_id)
            )
            if not db_job:
                return None
            job = CrawlJob(
                job_id=db_job.job_id,
                domain=db_job.hotel.domain,
                status=db_job.status,
                attempts=db_job.attempts,
                last_error=db_job.last_error,
                completed_at=db_job.completed_at,
                metadata=db_job.metadata or {},
                db_id=db_job.id,
            )
            return job

    async def get_discovered_links(self, job_id: str, limit: int) -> List[Dict]:
        async with session_scope() as session:
            result = await session.execute(
                select(DiscoveredLinkModel)
                .join(CrawlJobModel)
                .where(CrawlJobModel.job_id == job_id)
                .order_by(DiscoveredLinkModel.last_seen.desc())
                .limit(limit)
            )
            return [
                {
                    "url": row.url,
                    "source_url": row.source_url,
                    "network": row.network,
                    "last_seen": row.last_seen,
                }
                for row in result.scalars()
            ]

    async def reserve_next_job(self, queue: str) -> Optional[CrawlJob]:
        async with session_scope() as session:
            stmt: Select[CrawlJobModel] = (
                select(CrawlJobModel)
                .options(joinedload(CrawlJobModel.hotel))
                .where(CrawlJobModel.status.in_(["queued", "retry"]))
                .order_by(CrawlJobModel.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            result = await session.execute(stmt)
            db_job = result.scalar_one_or_none()
            if not db_job:
                return None

            db_job.status = "in_progress"
            db_job.attempts += 1
            await session.flush()

            job = CrawlJob(
                job_id=db_job.job_id,
                domain=db_job.hotel.domain,
                status=db_job.status,
                attempts=db_job.attempts,
                metadata=db_job.metadata or {},
                db_id=db_job.id,
            )

        await self._acquire_domain_slot(job.domain)
        IN_PROGRESS_JOBS.inc()
        return job

    async def _respect_domain_delay(self, domain: str) -> None:
        lock = self._domain_locks[domain]
        async with lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._domain_last_request[domain]
            delay = self.settings.per_domain_delay_seconds - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
            self._domain_last_request[domain] = asyncio.get_event_loop().time()

    async def _acquire_domain_slot(self, domain: str) -> None:
        semaphore = self._domain_semaphores[domain]
        await semaphore.acquire()

    async def _release_domain_slot(self, domain: str) -> None:
        semaphore = self._domain_semaphores[domain]
        semaphore.release()

    async def _record_fetch_attempt(
        self,
        job: CrawlJob,
        proxy: Optional[str],
        status_code: Optional[int],
        success: bool,
        error: Optional[str],
        response_time_ms: Optional[int],
    ) -> None:
        async with session_scope() as session:
            attempt = FetchAttemptModel(
                job_id=job.db_id,
                proxy=proxy,
                status_code=status_code,
                success=success,
                error=error[:5000] if error else None,
                response_time_ms=response_time_ms,
            )
            session.add(attempt)
        FETCH_ATTEMPTS_TOTAL.inc()

    async def process_job(
        self,
        job: CrawlJob,
        *,
        client: httpx.AsyncClient,
        browser: Browser,
        proxy: Optional[str],
    ) -> List[Dict]:
        await self._respect_domain_delay(job.domain)

        base_url = f"https://{job.domain}"
        start_time = time.perf_counter()
        try:
            response = await client.get(base_url, proxies=proxy)
            status_code = response.status_code
            html = response.text
        except Exception as exc:
            await self._record_fetch_attempt(
                job,
                proxy,
                status_code=None,
                success=False,
                error=str(exc),
                response_time_ms=None,
            )
            raise
        else:
            elapsed_seconds = time.perf_counter() - start_time
            elapsed_ms = int(elapsed_seconds * 1000)
            FETCH_LATENCY.observe(elapsed_seconds)
            success = status_code is not None and 200 <= status_code < 400
            error_msg = None if success else html[:500]
            await self._record_fetch_attempt(
                job,
                proxy,
                status_code=status_code,
                success=success,
                error=error_msg,
                response_time_ms=elapsed_ms,
            )

        if looks_like_captcha(html):
            raise RuntimeError("Encountered CAPTCHA")

        links_by_platform, others = parse_social_links(html, base_url)

        if is_js_heavy(html) and not any(links_by_platform.values()):
            page = await browser.new_page(proxy={"server": proxy} if proxy else None)
            try:
                await page.goto(
                    base_url,
                    wait_until="networkidle",
                    timeout=self.settings.request_timeout_seconds * 1000,
                )
                html = await page.content()
                links_by_platform, others = parse_social_links(html, base_url)
            finally:
                await page.close()

        results: List[Dict] = []
        for platform, urls in links_by_platform.items():
            for url in urls:
                results.append({"url": url, "network": platform, "source_url": base_url})
        for url in others:
            results.append({"url": url, "network": None, "source_url": base_url})

        return results

    async def mark_job_completed(self, job: CrawlJob, links: List[Dict]) -> None:
        async with session_scope() as session:
            db_job = await session.get(CrawlJobModel, job.db_id)
            if not db_job:
                return
            db_job.status = "completed"
            db_job.completed_at = datetime.utcnow()
            db_job.last_error = None

            for link in links:
                stmt = (
                    insert(DiscoveredLinkModel)
                    .values(
                        job_id=db_job.id,
                        url=link["url"],
                        network=link.get("network"),
                        source_url=link.get("source_url"),
                    )
                    .on_conflict_do_nothing(index_elements=[DiscoveredLinkModel.job_id, DiscoveredLinkModel.url])
                )
                await session.execute(stmt)
            LINKS_DISCOVERED_TOTAL.inc(len(links))

        await self._release_domain_slot(job.domain)
        IN_PROGRESS_JOBS.dec()

    async def mark_job_failed(self, job: CrawlJob, error: str) -> None:
        async with session_scope() as session:
            db_job = await session.get(CrawlJobModel, job.db_id)
            if not db_job:
                return
            if job.attempts >= self.settings.max_retries:
                db_job.status = "failed"
            else:
                db_job.status = "retry"
            db_job.last_error = error[:1000]
        await self._release_domain_slot(job.domain)
        IN_PROGRESS_JOBS.dec()


_global_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    global _global_manager
    if _global_manager is None:
        _global_manager = JobManager()
    return _global_manager


__all__ = ["JobManager", "get_job_manager"]
