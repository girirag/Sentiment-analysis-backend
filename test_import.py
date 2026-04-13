"""Test imports from backend directory"""
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    logger.info("Test 1: Import config...")
    from app.config import settings
    logger.info(f"✅ Config imported. Redis URL: {settings.redis_url}")
    
    logger.info("\nTest 2: Import Celery app...")
    from app.tasks.celery_tasks import celery_app
    logger.info(f"✅ Celery app imported: {celery_app}")
    
    logger.info("\nTest 3: Import task...")
    from app.tasks.celery_tasks import process_video_local_task
    logger.info(f"✅ Task imported: {process_video_local_task}")
    
    logger.info("\nTest 4: Check Celery connection...")
    inspect = celery_app.control.inspect()
    logger.info(f"✅ Inspect object created: {inspect}")
    
    logger.info("\nTest 5: Check active workers...")
    active = inspect.active()
    if active:
        logger.info(f"✅ Active workers found: {list(active.keys())}")
    else:
        logger.warning("⚠️  No active workers found")
    
    print("\n✅ All imports successful!")
    
except Exception as e:
    logger.error(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
