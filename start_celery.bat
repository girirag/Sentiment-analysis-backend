@echo off
celery -A app.tasks.celery_tasks worker --pool=solo --loglevel=info
