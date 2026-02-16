import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import io


class TestHealthEndpoints:
    """Test health and info endpoints"""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns API info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert data["version"] == "1.0.0"
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestVideoUploadEndpoint:
    """Test video upload endpoint"""
    
    @patch('app.api.routes.video.firebase_service')
    @patch('app.api.routes.video.process_video_task')
    def test_upload_video_success(self, mock_task, mock_firebase, client, auth_token):
        """Test successful video upload"""
        # Mock Firebase upload
        mock_firebase.upload_file.return_value = "gs://bucket/video.mp4"
        mock_firebase.create_video.return_value = "test_video_123"
        
        # Mock Celery task
        mock_task.delay.return_value = Mock(id="task_123")
        
        # Create a fake video file
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
        assert data["status"] == "queued"
    
    def test_upload_without_auth(self, client):
        """Test upload without authentication fails"""
        video_content = b"fake video content"
        files = {"file": ("test_video.mp4", io.BytesIO(video_content), "video/mp4")}
        
        response = client.post("/api/videos/upload", files=files)
        assert response.status_code == 401
    
    def test_upload_invalid_format(self, client, auth_token):
        """Test upload with invalid file format"""
        # Create a fake text file
        files = {"file": ("test.txt", io.BytesIO(b"text content"), "text/plain")}
        
        response = client.post(
            "/api/videos/upload",
            files=files,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should fail validation
        assert response.status_code in [400, 422]


class TestAnalysisEndpoints:
    """Test analysis retrieval endpoints"""
    
    @patch('app.api.routes.analysis.firebase_service')
    def test_get_analysis_success(self, mock_firebase, client, auth_token, sample_analysis_data):
        """Test successful analysis retrieval"""
        mock_firebase.get_analysis.return_value = sample_analysis_data
        
        response = client.get(
            "/api/analysis/test_video_123",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["video_id"] == "test_video_123"
        assert "overall_sentiment" in data
    
    @patch('app.api.routes.analysis.firebase_service')
    def test_get_analysis_not_found(self, mock_firebase, client, auth_token):
        """Test analysis retrieval for non-existent video"""
        mock_firebase.get_analysis.return_value = None
        
        response = client.get(
            "/api/analysis/nonexistent",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 404
    
    @patch('app.api.routes.analysis.firebase_service')
    def test_get_timeline(self, mock_firebase, client, auth_token):
        """Test timeline retrieval"""
        mock_firebase.get_analysis.return_value = {
            "timeline": [
                {"timestamp": 0.0, "sentiment": "positive", "score": 0.8}
            ]
        }
        
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
        """Test keywords retrieval"""
        mock_firebase.get_analysis.return_value = {
            "keywords": [
                {"keyword": "test", "count": 3, "timestamps": [1.0, 5.0, 10.0]}
            ]
        }
        
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
        """Test JSON export"""
        mock_firebase.get_analysis.return_value = sample_analysis_data
        
        response = client.get(
            "/api/analysis/test_video_123/export?format=json",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
    
    @patch('app.api.routes.analysis.firebase_service')
    def test_export_csv(self, mock_firebase, client, auth_token, sample_analysis_data):
        """Test CSV export"""
        mock_firebase.get_analysis.return_value = sample_analysis_data
        
        response = client.get(
            "/api/analysis/test_video_123/export?format=csv",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]


class TestErrorHandling:
    """Test error handling"""
    
    def test_404_not_found(self, client):
        """Test 404 error for non-existent endpoint"""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404
    
    def test_validation_error(self, client, auth_token):
        """Test validation error response format"""
        # Send invalid data
        response = client.post(
            "/api/videos/upload",
            headers={"Authorization": f"Bearer {auth_token}"}
            # Missing required file
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "error" in data or "detail" in data
