#!/bin/bash
set -e

echo "Starting Celery worker in background..."
celery -A app.tasks.celery_tasks:celery_app worker \
    --loglevel=info \
    --pool=solo \
    --concurrency=1 &

echo "Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
