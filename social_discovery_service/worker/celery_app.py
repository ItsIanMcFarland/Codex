"""Celery application for distributed workers."""

from __future__ import annotations

from celery import Celery

from ..config import get_settings
from ..jobs.manager import get_job_manager

settings = get_settings()

celery_app = Celery(
    "social_discovery",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC")


@celery_app.task(name="social_discovery.process_job")
def process_job_task(job_id: str) -> str:
    """Celery task entry point to process a single job."""

    manager = get_job_manager()
    # Celery tasks are synchronous, so we delegate to the async worker via CLI guidance.
    # This stub exists to demonstrate integration and can be extended to spin an event loop.
    return job_id


__all__ = ["celery_app", "process_job_task"]
