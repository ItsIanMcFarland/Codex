"""Entry points for running the FastAPI application."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router as api_router
from .config import get_settings
from .monitoring.metrics import metrics_router, setup_metrics

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(title="Social Discovery Service", version="0.1.0")
    app.include_router(api_router, prefix="/api")

    if settings.enable_metrics:
        setup_metrics()
        app.include_router(metrics_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"]
    )

    @app.on_event("startup")
    async def _on_startup() -> None:
        logger.info("Starting Social Discovery Service", extra={"environment": settings.environment})

    return app


app = create_app()

__all__ = ["create_app", "app"]
