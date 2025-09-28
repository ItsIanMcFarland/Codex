"""CLI entrypoint for the social discovery service."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer

from .config import Settings, get_settings
from .jobs.manager import JobManager, get_job_manager
from .worker.runner import run_worker

app = typer.Typer(help="Social Discovery Service command line interface")


@app.command()
def show_config() -> None:
    """Print the active configuration."""

    settings = get_settings()
    typer.echo(settings.json(indent=2))


@app.command()
def load_proxies(path: Path) -> None:
    """Load proxies from file and update the proxy pool."""

    manager = get_job_manager()
    count = manager.proxy_pool.load_from_file(path)
    typer.echo(f"Loaded {count} proxies from {path}")


@app.command()
def enqueue(
    batch_name: str,
    domains_file: Path = typer.Argument(..., exists=True, readable=True),
    metadata: Optional[str] = typer.Option(None, help="Optional metadata JSON string"),
) -> None:
    """Enqueue a batch of jobs from a newline separated file."""

    manager = get_job_manager()
    domains = [line.strip() for line in domains_file.read_text().splitlines() if line.strip()]
    payload_metadata = {}
    if metadata:
        import json

        payload_metadata = json.loads(metadata)

    batch = asyncio.run(manager.enqueue_batch(batch_name, domains, payload_metadata))
    typer.echo(f"Submitted batch {batch.batch_id} with {len(batch.jobs)} jobs")


@app.command()
def worker(
    queue: str = typer.Option("default", help="Queue name"),
    log_level: str = typer.Option("INFO", help="Logging level"),
    once: bool = typer.Option(False, help="Process a single job and exit"),
) -> None:
    """Run the async worker loop."""

    logging.basicConfig(level=log_level)
    settings = get_settings()
    manager = get_job_manager()
    asyncio.run(run_worker(manager, queue=queue, once=once, settings=settings))


@app.command()
def migrate(direction: str = typer.Argument("upgrade")) -> None:
    """Run Alembic migrations."""

    import subprocess

    settings: Settings = get_settings()
    subprocess.run(["alembic", "-c", str(settings.alembic_ini_path), direction], check=True)


if __name__ == "__main__":
    app()
