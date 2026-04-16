#!/bin/bash
set -e

# Ensure Python can find the app module from /app
export PYTHONPATH=/code:$PYTHONPATH

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

# Start FastAPI
APP_PORT="${PORT:-8000}"
echo "Starting FastAPI on port $APP_PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT"
