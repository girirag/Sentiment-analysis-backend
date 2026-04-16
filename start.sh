#!/bin/bash
set -e

# Start Celery worker in background (only if REDIS_URL is set)
if [ -n "$REDIS_URL" ]; then
    echo "Starting Celery worker..."
    celery -A app.tasks.celery_tasks:celery_app worker \
        --loglevel=info \
        --pool=solo \
        --concurrency=1 &
else
    echo "REDIS_URL not set, skipping Celery worker"
fi

# Start FastAPI — use PORT env var with fallback to 8000
APP_PORT="${PORT:-8000}"
echo "Starting FastAPI on port $APP_PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT"
