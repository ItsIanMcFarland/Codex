"""RQ worker helpers for distributed processing."""

from __future__ import annotations

import asyncio

from redis import Redis
from rq import Queue

from ..config import get_settings
from ..jobs.manager import get_job_manager
from .runner import run_worker


def process_single_job(job_id: str) -> None:
    manager = get_job_manager()
    settings = get_settings()
    asyncio.run(run_worker(manager, queue="default", once=True, settings=settings))


def enqueue_with_rq(job_id: str) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    queue = Queue("social_discovery", connection=redis)
    queue.enqueue(process_single_job, job_id)


__all__ = ["enqueue_with_rq", "process_single_job"]
