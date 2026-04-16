#!/bin/bash
# Start health server in background, then start Celery worker
python -c "from worker_health import start_health_server; start_health_server()" &
celery -A app.tasks.celery_tasks:celery_app worker --loglevel=info --pool=solo
