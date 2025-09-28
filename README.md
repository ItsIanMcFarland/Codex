# Social Discovery Service

The **Social Discovery Service** is an enterprise-ready microservice for discovering social media profiles for thousands of hotel domains. It combines an API-driven job queue, asyncio-based workers, and a PostgreSQL-backed persistence layer to operate safely at scale.

## Architecture Overview

- **API & CLI** – Submit discovery jobs via a FastAPI-powered REST interface or the Typer CLI.
- **Async Workers** – HTTPX + Playwright workers crawl hotel homepages, follow politeness policies, and normalize social links.
- **Distributed Scheduling** – Optional Celery/RQ integration enables horizontal worker scaling with Redis brokers.
- **Observability** – Structured logging, Prometheus metrics, and health endpoints for production monitoring.
- **Resilience** – Checkpointing, retry policies, proxy rotation, and per-domain rate limiting to handle flaky sites.
- **Security** – Role-based API keys gate access to administrative and submitter operations.

## Getting Started

### Prerequisites

- Python 3.11+
- Docker (optional but recommended for local orchestration)
- Playwright browsers (`playwright install --with-deps firefox`)

### Local Development (Docker Compose)

```bash
docker compose up --build
```

This launches the API, worker, PostgreSQL, and Redis. The API is available at `http://localhost:8000` and metrics at `http://localhost:8000/metrics`.

Seed jobs with the CLI:

```bash
docker compose run --rm api python -m social_discovery_service.cli enqueue demo-batch examples/hotels.csv --metadata '{"source": "demo"}'
```

Query job status:

```bash
curl -H "X-API-Key: admin-key" http://localhost:8000/api/jobs/<job_id>
```

### Running Locally Without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
playwright install --with-deps firefox
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/social_discovery
export REDIS_URL=redis://localhost:6379/0
export ADMIN_API_KEYS=local-admin
export SUBMITTER_API_KEYS=local-submitter
alembic upgrade head
uvicorn social_discovery_service.main:app --host 0.0.0.0 --port 8000
```

Start a worker in another terminal:

```bash
python -m social_discovery_service.cli worker
```

### CLI Commands

```bash
python -m social_discovery_service.cli --help
python -m social_discovery_service.cli show-config
python -m social_discovery_service.cli enqueue nightly examples/hotels.csv
python -m social_discovery_service.cli load-proxies proxies.txt
python -m social_discovery_service.cli migrate upgrade
```

### REST API

- `POST /api/jobs/batch` – Submit a batch of hotel domains (`X-API-Key` header required).
- `GET /api/jobs/{job_id}` – Inspect job status.
- `GET /api/jobs/{job_id}/results` – Retrieve discovered links.
- `GET /api/health` – Health check.
- `GET /metrics` – Prometheus metrics scrape endpoint.

OpenAPI docs: `http://localhost:8000/docs`

### Database Schema & Migrations

- Alembic migrations live in `social_discovery_service/db/migrations`.
- A printable schema snapshot is available at `social_discovery_service/db/schema.sql`.
- Run migrations with `python -m social_discovery_service.cli migrate upgrade` or via Docker entrypoint.

### Proxy Management

Provide a newline-separated list of SOCKS5/HTTPS proxies. Proxies are rotated automatically and quarantined after repeated failures. Load proxies through the CLI:

```bash
python -m social_discovery_service.cli load-proxies config/proxies.txt
```

### Distributed Workers

- **Celery**: Import `social_discovery_service.worker.celery_app` in your worker deployment. Extend `process_job_task` to orchestrate async workers or schedule CLI executions.
- **RQ**: Use `social_discovery_service.worker.rq_worker.enqueue_with_rq(job_id)` to drop jobs onto an RQ queue.

### Monitoring & Alerts

Key Prometheus metrics:

- `social_discovery_fetch_attempts_total`
- `social_discovery_fetch_latency_seconds`
- `social_discovery_links_discovered_total`
- `social_discovery_jobs_in_progress`
- `social_discovery_worker_errors_total`

Integrate the sample `ServiceMonitor` in `deploy/k8s/social-discovery.yaml` for Prometheus Operator setups.

### Load Testing

A simple Locust script lives in `load_tests/locustfile.py`:

```bash
locust -f load_tests/locustfile.py --host http://localhost:8000
```

Tune RPS to estimate capacity; 10 worker pods typically sustain ~1k domains/hour assuming 3 HTTP fetches/domain and commodity proxies. Budget proxy bandwidth (~1 GB per 5k domains) and Playwright CPU (1 core per active worker).

### Kubernetes Deployment

Use `deploy/k8s/social-discovery.yaml` as a baseline. It deploys API and worker deployments, service definitions, and a Prometheus `ServiceMonitor`. Inject secrets via `social-discovery-secrets` for database credentials and API keys.

### Test Data & Expected Output

Sample hotel domains live in `examples/hotels.csv`. After enqueuing the sample batch, `GET /api/jobs/{job_id}/results` returns normalized social links with platform metadata. `tests/` contains unit tests for the HTML parser and storage helpers inherited from the legacy project.

### Cost & Throughput Guidance

- **Workers**: Start with 2 CPU / 4 GB RAM per worker pod when Playwright rendering is enabled.
- **Database**: PostgreSQL `db.m6g.large`-class instances comfortably handle ~50 req/s with the provided indexes.
- **Redis**: A single cache.m6g.large handles queue fan-out for thousands of jobs.
- **Bandwidth**: Expect ~200 KB per fetch; plan proxies accordingly.

### Security Notes

- API requests must include `X-API-Key` matching a configured admin or submitter key.
- Do **not** attempt CAPTCHA bypass; jobs encountering CAPTCHAs are marked failed for manual review.
- Enable TLS and perimeter firewalls in production environments.

## Repository Layout

```
├── Dockerfile
├── docker-compose.yml
├── docker/entrypoint.sh
├── deploy/k8s/
├── social_discovery_service/
│   ├── api/
│   ├── config.py
│   ├── cli.py
│   ├── db/
│   ├── jobs/
│   ├── monitoring/
│   ├── security/
│   └── worker/
├── load_tests/
├── hotel_social_discover/  # HTML parsing + heuristics
└── tests/
```

## License

MIT
