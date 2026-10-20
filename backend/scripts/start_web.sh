#!/bin/sh
set -eu
uv run python -m app.core.deployment
uv run alembic upgrade head
exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
