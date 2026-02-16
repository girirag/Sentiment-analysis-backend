"""Simple test without Firebase dependency"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("Simple Backend Test (No Firebase Required)")
print("=" * 60)

# Test 1: Models
print("\n1. Testing Pydantic Models...")
try:
    from app.models.schemas import (
        VideoUploadResponse,
        SentimentResult,
        KeywordData,
        TimelinePoint,
        TranscriptionSegment,
        Word
    )
    
    # Create test instances
    response = VideoUploadResponse(video_id="test", status="queued", message="OK")
    sentiment = SentimentResult(sentiment="positive", score=0.8, confidence=0.9, timestamp=10.0)
    word = Word(word="hello", start=0.0, end=0.5)
    segment = TranscriptionSegment(text="Hello world", start=0.0, end=1.0, words=[word])
    
    print("✅ All models work correctly")
except Exception as e:
    print(f"❌ Models test failed: {e}")
    sys.exit(1)

# Test 2: Configuration
print("\n2. Testing Configuration...")
try:
    from app.config import settings
    print(f"  - Whisper model: {settings.whisper_model}")
    print(f"  - Max video size: {settings.max_video_size_mb}MB")
    print(f"  - Redis URL: {settings.redis_url}")
    print("✅ Configuration loaded successfully")
except Exception as e:
    print(f"❌ Configuration test failed: {e}")
    sys.exit(1)

# Test 3: Service Classes (without initialization)
print("\n3. Testing Service Classes...")
try:
    from app.services.video_processor import VideoProcessor
    from app.services.sentiment_analyzer import SentimentAnalyzer
    from app.services.keyword_tracker import KeywordTracker
    
    # Just check they can be imported
    print("  - VideoProcessor: OK")
    print("  - SentimentAnalyzer: OK")
    print("  - KeywordTracker: OK")
    print("✅ Service classes imported successfully")
except Exception as e:
    print(f"❌ Service classes test failed: {e}")
    sys.exit(1)

# Test 4: API Routes
print("\n4. Testing API Routes...")
try:
    from app.api.routes import video, analysis
    print("  - Video routes: OK")
    print("  - Analysis routes: OK")
    print("✅ API routes imported successfully")
except Exception as e:
    print(f"❌ API routes test failed: {e}")
    sys.exit(1)

# Test 5: Celery Tasks
print("\n5. Testing Celery Configuration...")
try:
    from app.tasks.celery_tasks import celery_app
    print(f"  - Celery app: {celery_app.main}")
    print(f"  - Broker: {celery_app.conf.broker_url}")
    print("✅ Celery configured successfully")
except Exception as e:
    print(f"❌ Celery test failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ All tests passed!")
print("=" * 60)
print("\nBackend structure is correct and ready to run.")
print("\nNext steps:")
print("1. Install dependencies: pip install -r requirements.txt")
print("2. Configure Firebase credentials (firebase-key.json)")
print("3. Start Redis: docker run -d -p 6379:6379 redis:7-alpine")
print("4. Start backend: uvicorn app.main:app --reload")
print("5. Start Celery: celery -A app.tasks.celery_tasks worker --loglevel=info")
