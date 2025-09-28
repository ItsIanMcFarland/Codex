"""Prometheus metrics and monitoring utilities."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

FETCH_ATTEMPTS_TOTAL = Counter("social_discovery_fetch_attempts_total", "Total fetch attempts")
LINKS_DISCOVERED_TOTAL = Counter("social_discovery_links_discovered_total", "Total links discovered")
WORKER_ERRORS = Counter("social_discovery_worker_errors_total", "Worker level exceptions")
WORKER_JOBS_COMPLETED = Counter("social_discovery_jobs_completed_total", "Jobs completed successfully")
WORKER_JOBS_FAILED = Counter("social_discovery_jobs_failed_total", "Jobs completed without links")
IN_PROGRESS_JOBS = Gauge("social_discovery_jobs_in_progress", "Current in-progress jobs")
FETCH_LATENCY = Histogram("social_discovery_fetch_latency_seconds", "Latency for HTTP fetches")

metrics_router = APIRouter()


@metrics_router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def setup_metrics() -> None:
    """Placeholder to register custom collectors when the service starts."""

    # No-op for now. This function exists for future extensions.
    return None


__all__ = [
    "FETCH_ATTEMPTS_TOTAL",
    "LINKS_DISCOVERED_TOTAL",
    "WORKER_ERRORS",
    "WORKER_JOBS_COMPLETED",
    "WORKER_JOBS_FAILED",
    "IN_PROGRESS_JOBS",
    "FETCH_LATENCY",
    "metrics_router",
    "setup_metrics",
]
