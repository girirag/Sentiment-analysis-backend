import pytest
from fastapi.testclient import TestClient
from app.main import app
import os

@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)

@pytest.fixture
def auth_token():
    """Mock authentication token"""
    return "test_token_123"

@pytest.fixture
def mock_video_id():
    """Mock video ID for testing"""
    return "test_video_123"

@pytest.fixture
def sample_video_data():
    """Sample video data for testing"""
    return {
        "video_id": "test_video_123",
        "title": "Test Video",
        "status": "completed",
        "created_at": "2024-01-01T00:00:00Z",
        "duration": 120
    }

@pytest.fixture
def sample_analysis_data():
    """Sample analysis data for testing"""
    return {
        "video_id": "test_video_123",
        "overall_sentiment": "positive",
        "sentiment_score": 0.75,
        "confidence": 0.92,
        "transcription": "This is a test transcription",
        "timeline": [
            {"timestamp": 0.0, "sentiment": "positive", "score": 0.8},
            {"timestamp": 5.0, "sentiment": "positive", "score": 0.7}
        ],
        "keywords": [
            {"keyword": "test", "count": 3, "timestamps": [1.0, 5.0, 10.0]}
        ]
    }
