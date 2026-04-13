import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

# Force development mode so verify_auth_token bypasses Firebase
os.environ["ENVIRONMENT"] = "development"
os.environ["DEBUG"] = "true"

from app.main import app
from app.api.dependencies import verify_auth_token


def make_auth_override(require_header: bool = True):
    """Return a dependency override for verify_auth_token."""
    async def _override(authorization: str = None):
        if require_header and authorization is None:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header"
            )
        return {
            "uid": "test-user-123",
            "email": "test@example.com",
            "name": "Test User"
        }
    return _override


@pytest.fixture
def client():
    """Test client with auth dependency overridden — requires Authorization header."""
    from fastapi import Header
    from typing import Optional

    async def mock_auth(authorization: Optional[str] = Header(None)):
        if authorization is None:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header"
            )
        return {
            "uid": "test-user-123",
            "email": "test@example.com",
            "name": "Test User"
        }

    app.dependency_overrides[verify_auth_token] = mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_token():
    """Mock authentication token"""
    return "test_token_123"


@pytest.fixture
def mock_video_id():
    return "test_video_123"


@pytest.fixture
def sample_video_data():
    return {
        "video_id": "test_video_123",
        "title": "Test Video",
        "status": "completed",
        "created_at": "2024-01-01T00:00:00Z",
        "duration": 120
    }


@pytest.fixture
def sample_analysis_data():
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
