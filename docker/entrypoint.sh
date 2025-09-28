#!/bin/bash
set -euo pipefail

alembic -c /app/alembic.ini upgrade head
uvicorn social_discovery_service.main:app --host 0.0.0.0 --port 8000
