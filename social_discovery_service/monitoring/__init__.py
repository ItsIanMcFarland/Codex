"""Monitoring helpers."""

from .metrics import (
    FETCH_ATTEMPTS_TOTAL,
    FETCH_LATENCY,
    IN_PROGRESS_JOBS,
    LINKS_DISCOVERED_TOTAL,
    WORKER_ERRORS,
    WORKER_JOBS_COMPLETED,
    WORKER_JOBS_FAILED,
    metrics_router,
    setup_metrics,
)

__all__ = [
    "FETCH_ATTEMPTS_TOTAL",
    "FETCH_LATENCY",
    "IN_PROGRESS_JOBS",
    "LINKS_DISCOVERED_TOTAL",
    "WORKER_ERRORS",
    "WORKER_JOBS_COMPLETED",
    "WORKER_JOBS_FAILED",
    "metrics_router",
    "setup_metrics",
]
