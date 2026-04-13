import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import io


class TestHealthEndpoints:
    """Test health and info endpoints"""

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert data["version"] == "1.0.0"

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestVideoUploadEndpoint:
    """Test video upload endpoint"""

    @patch('app.api.routes.video.process_video_local_task')
    def test_upload_video_success(self, mock_task, client, auth_token):
        """Test successful video upload in dev mode"""
        mock_task.delay.return_value = Mock(id="task_123")

        video_content = b"fake video content"
        files = {"file": ("test_video.mp4", io.BytesIO(video_content), "video/mp4")}

        response = client.post(
            "/api/videos/upload",
            files=files,
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "video_id" in data

    def test_upload_without_auth(self, client):
        """Test upload without authentication fails with 401"""
        video_content = b"fake video content"
        files = {"file": ("test_video.mp4", io.BytesIO(video_content), "video/mp4")}

        # No Authorization header — dependency override raises 401 for None
        response = client.post("/api/videos/upload", files=files)
        assert response.status_code == 401

    def test_upload_invalid_format(self, client, auth_token):
        """Test upload with invalid file format returns 400 or 422"""
        files = {"file": ("test.txt", io.BytesIO(b"text content"), "text/plain")}

        response = client.post(
            "/api/videos/upload",
            files=files,
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code in [400, 422]


class TestAnalysisEndpoints:
    """Test analysis retrieval endpoints"""

    @patch('app.api.routes.analysis.firebase_service')
    def test_get_analysis_success(self, mock_firebase, client, auth_token, sample_analysis_data):
        mock_firebase.get_analysis = AsyncMock(return_value=sample_analysis_data)

        response = client.get(
            "/api/analysis/test_video_123",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "video_id" in data or "overall_sentiment" in data

    @patch('app.api.routes.analysis.firebase_service')
    def test_get_analysis_not_found(self, mock_firebase, client, auth_token):
        mock_firebase.get_analysis = AsyncMock(return_value=None)

        response = client.get(
            "/api/analysis/nonexistent",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 404

    @patch('app.api.routes.analysis.firebase_service')
    def test_get_timeline(self, mock_firebase, client, auth_token):
        mock_firebase.get_analysis = AsyncMock(return_value={
            "timeline": [
                {"timestamp": 0.0, "sentiment": "positive", "score": 0.8}
            ]
        })

        response = client.get(
            "/api/analysis/test_video_123/timeline",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "timeline" in data
        assert len(data["timeline"]) > 0

    @patch('app.api.routes.analysis.firebase_service')
    def test_get_keywords(self, mock_firebase, client, auth_token):
        mock_firebase.get_analysis = AsyncMock(return_value={
            "keywords": [
                {"keyword": "test", "count": 3, "timestamps": [1.0, 5.0, 10.0]}
            ]
        })

        response = client.get(
            "/api/analysis/test_video_123/keywords",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "keywords" in data
        assert len(data["keywords"]) > 0


class TestExportEndpoint:
    """Test export functionality"""

    @patch('app.api.routes.analysis.firebase_service')
    def test_export_json(self, mock_firebase, client, auth_token, sample_analysis_data):
        mock_firebase.get_analysis = AsyncMock(return_value=sample_analysis_data)

        response = client.get(
            "/api/analysis/test_video_123/export?format=json",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    @patch('app.api.routes.analysis.firebase_service')
    def test_export_csv(self, mock_firebase, client, auth_token, sample_analysis_data):
        mock_firebase.get_analysis = AsyncMock(return_value=sample_analysis_data)

        response = client.get(
            "/api/analysis/test_video_123/export?format=csv",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]


class TestErrorHandling:
    """Test error handling"""

    def test_404_not_found(self, client):
        """Test 404 for a truly non-existent route — use a path outside all registered prefixes"""
        response = client.get("/nonexistent-path-xyz-123")
        assert response.status_code == 404

    def test_validation_error(self, client, auth_token):
        """Test missing required file returns 422"""
        response = client.post(
            "/api/videos/upload",
            headers={"Authorization": f"Bearer {auth_token}"}
            # No file attached — should trigger 422 validation error
        )

        assert response.status_code == 422
        data = response.json()
        assert "error" in data or "detail" in data
