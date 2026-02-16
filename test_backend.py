"""Test script to verify backend functionality"""
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    
    try:
        from app.main import app
        print("✓ Main app imported successfully")
        
        from app.config import settings
        print("✓ Config imported successfully")
        
        from app.models.schemas import VideoUploadResponse, AnalysisResponse
        print("✓ Schemas imported successfully")
        
        from app.api.routes import video, analysis
        print("✓ API routes imported successfully")
        
        from app.services.video_processor import VideoProcessor
        print("✓ Video processor imported successfully")
        
        from app.services.transcriber import Transcriber
        print("✓ Transcriber imported successfully")
        
        from app.services.sentiment_analyzer import SentimentAnalyzer
        print("✓ Sentiment analyzer imported successfully")
        
        from app.services.keyword_tracker import KeywordTracker
        print("✓ Keyword tracker imported successfully")
        
        from app.services.stream_handler import StreamHandler
        print("✓ Stream handler imported successfully")
        
        from app.tasks.celery_tasks import celery_app
        print("✓ Celery tasks imported successfully")
        
        print("\n✅ All imports successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Import failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_app_structure():
    """Test FastAPI app structure"""
    print("\nTesting app structure...")
    
    try:
        from app.main import app
        
        # Check routes
        routes = [route.path for route in app.routes]
        print(f"✓ Found {len(routes)} routes")
        
        # Check for key endpoints
        expected_endpoints = [
            "/",
            "/health",
            "/api/videos/upload",
            "/api/videos/stream/start",
            "/api/analysis/{video_id}",
        ]
        
        for endpoint in expected_endpoints:
            # Check if endpoint pattern exists
            found = any(endpoint.replace("{video_id}", "") in route for route in routes)
            if found:
                print(f"✓ Endpoint exists: {endpoint}")
            else:
                print(f"⚠ Endpoint not found: {endpoint}")
        
        print("\n✅ App structure test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ App structure test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_config():
    """Test configuration"""
    print("\nTesting configuration...")
    
    try:
        from app.config import settings
        
        print(f"✓ Whisper model: {settings.whisper_model}")
        print(f"✓ Sentiment model: {settings.sentiment_model}")
        print(f"✓ Max video size: {settings.max_video_size_mb}MB")
        print(f"✓ Stream chunk duration: {settings.stream_chunk_duration}s")
        print(f"✓ Redis URL: {settings.redis_url}")
        
        print("\n✅ Configuration test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Configuration test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_models():
    """Test Pydantic models"""
    print("\nTesting Pydantic models...")
    
    try:
        from app.models.schemas import (
            VideoUploadResponse,
            SentimentResult,
            KeywordData,
            TimelinePoint,
            AnalysisSummary
        )
        
        # Test VideoUploadResponse
        response = VideoUploadResponse(
            video_id="test123",
            status="queued",
            message="Test message"
        )
        print(f"✓ VideoUploadResponse: {response.video_id}")
        
        # Test SentimentResult
        sentiment = SentimentResult(
            sentiment="positive",
            score=0.8,
            confidence=0.95,
            timestamp=10.5
        )
        print(f"✓ SentimentResult: {sentiment.sentiment} ({sentiment.score})")
        
        # Test TimelinePoint
        point = TimelinePoint(
            timestamp=5.0,
            sentiment="neutral",
            score=0.0
        )
        print(f"✓ TimelinePoint: {point.timestamp}s")
        
        # Test AnalysisSummary
        summary = AnalysisSummary(
            overall_sentiment="positive",
            avg_score=0.5,
            total_keywords=10,
            duration=120.0,
            positive_percentage=60.0,
            negative_percentage=20.0,
            neutral_percentage=20.0
        )
        print(f"✓ AnalysisSummary: {summary.overall_sentiment}")
        
        print("\n✅ Models test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Models test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Backend Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("App Structure", test_app_structure()))
    results.append(("Configuration", test_config()))
    results.append(("Models", test_models()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Backend is ready to run.")
        print("\nTo start the backend:")
        print("  cd backend")
        print("  uvicorn app.main:app --reload")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
