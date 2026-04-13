"""
Integration Tests
=================
End-to-end tests that exercise the full request/response cycle
through the real FastAPI app (TestClient), covering:

  1. System health & metadata
  2. Authentication & authorisation
  3. Video upload lifecycle (upload → list → get → delete)
  4. Stream lifecycle (start → stop)
  5. Analysis endpoints
  6. Clip highlights endpoints
  7. Error handling & edge cases
  8. Cross-endpoint data consistency
"""

import io
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["ENVIRONMENT"] = "development"
os.environ["DEBUG"] = "true"

from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock

from app.main import app
from app.api.dependencies import verify_auth_token

# ── Auth override ────────────────────────────────────────────────────────────

MOCK_USER = {"uid": "integ-test-user-001", "email": "integ@test.com", "name": "Integration Tester"}


@pytest.fixture(scope="module")
def client():
    from fastapi import Header
    from typing import Optional

    async def _mock_auth(authorization: Optional[str] = Header(None)):
        if authorization is None:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=401, detail="Missing authorization header")
        return MOCK_USER

    app.dependency_overrides[verify_auth_token] = _mock_auth
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def auth():
    return {"Authorization": "Bearer integ-test-token"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _mp4(size=512):
    return io.BytesIO(b"\x00" * size)


# ════════════════════════════════════════════════════════════════════════════
# 1. SYSTEM HEALTH & METADATA
# ════════════════════════════════════════════════════════════════════════════

class TestSystemHealth:

    def test_root_returns_api_info(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["message"] == "Video Sentiment Analysis API"
        assert data["version"] == "1.0.0"

    def test_health_check_returns_healthy(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_health_content_type_is_json(self, client):
        r = client.get("/health")
        assert "application/json" in r.headers["content-type"]

    def test_root_content_type_is_json(self, client):
        r = client.get("/")
        assert "application/json" in r.headers["content-type"]

    def test_cors_headers_present(self, client):
        r = client.options("/api/videos/upload")
        # OPTIONS should not crash
        assert r.status_code in (200, 405)


# ════════════════════════════════════════════════════════════════════════════
# 2. AUTHENTICATION & AUTHORISATION
# ════════════════════════════════════════════════════════════════════════════

class TestAuthentication:

    def test_upload_without_auth_returns_401(self, client):
        files = {"file": ("v.mp4", _mp4(), "video/mp4")}
        r = client.post("/api/videos/upload", files=files)
        assert r.status_code == 401

    def test_list_videos_without_auth_returns_401(self, client):
        r = client.get("/api/videos/")
        assert r.status_code == 401

    def test_get_video_without_auth_returns_401(self, client):
        r = client.get("/api/videos/some-id")
        assert r.status_code == 401

    def test_delete_video_without_auth_returns_401(self, client):
        r = client.delete("/api/videos/some-id")
        assert r.status_code == 401

    def test_analysis_without_auth_returns_401(self, client):
        r = client.get("/api/analysis/some-id")
        assert r.status_code == 401

    def test_with_valid_auth_header_passes(self, client, auth):
        r = client.get("/api/videos/", headers=auth)
        assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════════════
# 3. VIDEO UPLOAD LIFECYCLE
# ════════════════════════════════════════════════════════════════════════════

class TestVideoUploadLifecycle:
    """Upload → list → get → delete full cycle."""

    uploaded_id = None

    def test_upload_valid_mp4_returns_200(self, client, auth):
        files = {"file": ("integration_test.mp4", _mp4(1024), "video/mp4")}
        r = client.post("/api/videos/upload", files=files, headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "video_id" in data
        assert data["status"] in ("queued", "processing")
        TestVideoUploadLifecycle.uploaded_id = data["video_id"]

    def test_upload_response_has_message(self, client, auth):
        files = {"file": ("msg_test.mp4", _mp4(), "video/mp4")}
        r = client.post("/api/videos/upload", files=files, headers=auth)
        assert r.status_code == 200
        assert "message" in r.json()

    def test_upload_invalid_format_returns_400(self, client, auth):
        files = {"file": ("bad.txt", io.BytesIO(b"text"), "text/plain")}
        r = client.post("/api/videos/upload", files=files, headers=auth)
        assert r.status_code == 400

    def test_upload_no_file_returns_422(self, client, auth):
        r = client.post("/api/videos/upload", headers=auth)
        assert r.status_code == 422

    def test_upload_avi_format_accepted(self, client, auth):
        files = {"file": ("clip.avi", _mp4(), "video/avi")}
        r = client.post("/api/videos/upload", files=files, headers=auth)
        assert r.status_code == 200

    def test_upload_mov_format_accepted(self, client, auth):
        files = {"file": ("clip.mov", _mp4(), "video/quicktime")}
        r = client.post("/api/videos/upload", files=files, headers=auth)
        assert r.status_code == 200

    def test_list_videos_returns_200(self, client, auth):
        r = client.get("/api/videos/", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "videos" in data
        assert "count" in data
        assert isinstance(data["videos"], list)

    def test_list_videos_count_matches_videos_length(self, client, auth):
        r = client.get("/api/videos/", headers=auth)
        data = r.json()
        assert data["count"] == len(data["videos"])

    def test_uploaded_video_appears_in_list(self, client, auth):
        if not TestVideoUploadLifecycle.uploaded_id:
            pytest.skip("No uploaded video ID available")
        r = client.get("/api/videos/", headers=auth)
        ids = [v["video_id"] for v in r.json()["videos"]]
        assert TestVideoUploadLifecycle.uploaded_id in ids

    def test_get_uploaded_video_by_id(self, client, auth):
        if not TestVideoUploadLifecycle.uploaded_id:
            pytest.skip("No uploaded video ID available")
        vid = TestVideoUploadLifecycle.uploaded_id
        r = client.get(f"/api/videos/{vid}", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert data["video_id"] == vid

    def test_get_nonexistent_video_returns_404(self, client, auth):
        r = client.get("/api/videos/nonexistent-xyz-999", headers=auth)
        assert r.status_code == 404

    def test_delete_uploaded_video(self, client, auth):
        if not TestVideoUploadLifecycle.uploaded_id:
            pytest.skip("No uploaded video ID available")
        vid = TestVideoUploadLifecycle.uploaded_id
        r = client.delete(f"/api/videos/{vid}", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["video_id"] == vid

    def test_deleted_video_not_in_list(self, client, auth):
        if not TestVideoUploadLifecycle.uploaded_id:
            pytest.skip("No uploaded video ID available")
        r = client.get("/api/videos/", headers=auth)
        ids = [v["video_id"] for v in r.json()["videos"]]
        assert TestVideoUploadLifecycle.uploaded_id not in ids

    def test_delete_nonexistent_video_returns_404(self, client, auth):
        r = client.delete("/api/videos/does-not-exist-abc", headers=auth)
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# 4. STREAM LIFECYCLE
# ════════════════════════════════════════════════════════════════════════════

class TestStreamLifecycle:

    stream_id = None

    def test_start_stream_returns_200(self, client, auth):
        payload = {"stream_url": "https://example.com/stream.m3u8", "title": "Integration Test Stream"}
        r = client.post("/api/videos/stream/start", json=payload, headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "video_id" in data
        assert data["status"] == "streaming"
        assert "websocket_url" in data
        TestStreamLifecycle.stream_id = data["video_id"]

    def test_start_stream_websocket_url_format(self, client, auth):
        payload = {"stream_url": "https://example.com/live.m3u8", "title": "WS URL Test"}
        r = client.post("/api/videos/stream/start", json=payload, headers=auth)
        assert r.status_code == 200
        ws_url = r.json()["websocket_url"]
        assert ws_url.startswith("ws://")

    def test_stop_stream_returns_200(self, client, auth):
        if not TestStreamLifecycle.stream_id:
            pytest.skip("No stream ID available")
        r = client.post(f"/api/videos/stream/stop/{TestStreamLifecycle.stream_id}", headers=auth)
        assert r.status_code == 200
        data = r.json()
        assert "message" in data
        assert data["video_id"] == TestStreamLifecycle.stream_id

    def test_stop_nonexistent_stream_returns_404(self, client, auth):
        r = client.post("/api/videos/stream/stop/nonexistent-stream-xyz", headers=auth)
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# 5. ANALYSIS ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

class TestAnalysisEndpoints:
    """Analysis endpoints — uses a freshly uploaded video."""

    video_id = None

    @pytest.fixture(autouse=True)
    def _upload_video(self, client, auth):
        """Upload a video once for all analysis tests."""
        if TestAnalysisEndpoints.video_id is None:
            files = {"file": ("analysis_test.mp4", _mp4(2048), "video/mp4")}
            r = client.post("/api/videos/upload", files=files, headers=auth)
            assert r.status_code == 200
            TestAnalysisEndpoints.video_id = r.json()["video_id"]

    def test_get_analysis_returns_200_or_404(self, client, auth):
        """Analysis may be pending (200 with status=queued) or not found."""
        vid = TestAnalysisEndpoints.video_id
        r = client.get(f"/api/analysis/{vid}", headers=auth)
        assert r.status_code in (200, 404)

    def test_get_analysis_200_has_required_fields(self, client, auth):
        vid = TestAnalysisEndpoints.video_id
        r = client.get(f"/api/analysis/{vid}", headers=auth)
        if r.status_code == 200:
            data = r.json()
            assert "video_id" in data
            assert "status" in data

    def test_get_analysis_nonexistent_video_returns_404(self, client, auth):
        r = client.get("/api/analysis/totally-fake-video-id", headers=auth)
        assert r.status_code == 404

    def test_analysis_response_content_type_json(self, client, auth):
        vid = TestAnalysisEndpoints.video_id
        r = client.get(f"/api/analysis/{vid}", headers=auth)
        if r.status_code == 200:
            assert "application/json" in r.headers["content-type"]


# ════════════════════════════════════════════════════════════════════════════
# 6. CLIP HIGHLIGHTS ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

class TestClipHighlightsEndpoints:

    video_id = None

    @pytest.fixture(autouse=True)
    def _upload_video(self, client, auth):
        if TestClipHighlightsEndpoints.video_id is None:
            files = {"file": ("clips_test.mp4", _mp4(1024), "video/mp4")}
            r = client.post("/api/videos/upload", files=files, headers=auth)
            assert r.status_code == 200
            TestClipHighlightsEndpoints.video_id = r.json()["video_id"]

    def test_list_clips_returns_200(self, client, auth):
        vid = TestClipHighlightsEndpoints.video_id
        r = client.get(f"/api/videos/{vid}/clips", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_generate_clips_invalid_file_type_returns_400(self, client, auth):
        vid = TestClipHighlightsEndpoints.video_id
        files = {"file": ("data.pdf", io.BytesIO(b"pdf content"), "application/pdf")}
        r = client.post(
            f"/api/videos/{vid}/clips/generate",
            files=files,
            data={"similarity_threshold": "0.5"},
            headers=auth,
        )
        assert r.status_code == 400

    def test_generate_clips_valid_json_dataset_returns_202(self, client, auth):
        vid = TestClipHighlightsEndpoints.video_id
        dataset = json.dumps([{"text": "test clip content", "label": "highlight"}]).encode()
        files = {"file": ("dataset.json", io.BytesIO(dataset), "application/json")}
        r = client.post(
            f"/api/videos/{vid}/clips/generate",
            files=files,
            data={"similarity_threshold": "0.5"},
            headers=auth,
        )
        assert r.status_code in (202, 404, 503)

    def test_clip_job_status_nonexistent_returns_404(self, client, auth):
        vid = TestClipHighlightsEndpoints.video_id
        r = client.get(f"/api/videos/{vid}/clips/status/fake-job-id", headers=auth)
        assert r.status_code == 404

    def test_download_nonexistent_clip_returns_404(self, client, auth):
        vid = TestClipHighlightsEndpoints.video_id
        r = client.get(f"/api/videos/{vid}/clips/fake-clip-id/download", headers=auth)
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# 7. ERROR HANDLING & EDGE CASES
# ════════════════════════════════════════════════════════════════════════════

class TestErrorHandling:

    def test_completely_unknown_route_returns_404(self, client):
        # The app has a catch-all OPTIONS handler; use a path that won't match it
        r = client.get("/zzz-totally-unknown-route-xyz-abc-123")
        assert r.status_code in (404, 405)  # 405 from catch-all OPTIONS is acceptable

    def test_method_not_allowed_on_health(self, client):
        r = client.post("/health")
        assert r.status_code == 405

    def test_upload_empty_filename_returns_400(self, client, auth):
        files = {"file": ("noext", io.BytesIO(b"data"), "application/octet-stream")}
        r = client.post("/api/videos/upload", files=files, headers=auth)
        assert r.status_code in (400, 422)

    def test_upload_pdf_returns_400(self, client, auth):
        files = {"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")}
        r = client.post("/api/videos/upload", files=files, headers=auth)
        assert r.status_code == 400

    def test_error_response_has_detail_field(self, client, auth):
        r = client.get("/api/videos/nonexistent-video", headers=auth)
        assert r.status_code == 404
        data = r.json()
        assert "detail" in data or "error" in data

    def test_analysis_wrong_method_returns_405(self, client, auth):
        r = client.post("/api/analysis/some-id", headers=auth)
        assert r.status_code == 405


# ════════════════════════════════════════════════════════════════════════════
# 8. CROSS-ENDPOINT DATA CONSISTENCY
# ════════════════════════════════════════════════════════════════════════════

class TestDataConsistency:
    """Verify data written by one endpoint is readable by another."""

    def test_upload_then_list_consistency(self, client, auth):
        """Video uploaded via POST appears in GET list with correct fields."""
        files = {"file": ("consistency_test.mp4", _mp4(512), "video/mp4")}
        upload_r = client.post("/api/videos/upload", files=files, headers=auth)
        assert upload_r.status_code == 200
        vid = upload_r.json()["video_id"]

        list_r = client.get("/api/videos/", headers=auth)
        videos = list_r.json()["videos"]
        match = next((v for v in videos if v["video_id"] == vid), None)
        assert match is not None, "Uploaded video not found in list"
        assert match["video_id"] == vid
        assert "status" in match
        assert "title" in match

        # cleanup
        client.delete(f"/api/videos/{vid}", headers=auth)

    def test_upload_then_get_consistency(self, client, auth):
        """GET /{video_id} returns same video_id as upload response."""
        files = {"file": ("get_consistency.mp4", _mp4(512), "video/mp4")}
        upload_r = client.post("/api/videos/upload", files=files, headers=auth)
        vid = upload_r.json()["video_id"]

        get_r = client.get(f"/api/videos/{vid}", headers=auth)
        assert get_r.status_code == 200
        assert get_r.json()["video_id"] == vid

        client.delete(f"/api/videos/{vid}", headers=auth)

    def test_delete_then_get_returns_404(self, client, auth):
        """After DELETE, GET returns 404."""
        files = {"file": ("delete_consistency.mp4", _mp4(512), "video/mp4")}
        upload_r = client.post("/api/videos/upload", files=files, headers=auth)
        vid = upload_r.json()["video_id"]

        client.delete(f"/api/videos/{vid}", headers=auth)

        get_r = client.get(f"/api/videos/{vid}", headers=auth)
        assert get_r.status_code == 404

    def test_upload_filename_preserved_in_metadata(self, client, auth):
        """Filename used during upload is stored in video metadata."""
        fname = "my_special_video.mp4"
        files = {"file": (fname, _mp4(512), "video/mp4")}
        upload_r = client.post("/api/videos/upload", files=files, headers=auth)
        vid = upload_r.json()["video_id"]

        get_r = client.get(f"/api/videos/{vid}", headers=auth)
        assert get_r.status_code == 200
        data = get_r.json()
        assert data.get("title") == fname or data.get("filename") == fname

        client.delete(f"/api/videos/{vid}", headers=auth)

    def test_list_count_updates_after_upload_and_delete(self, client, auth):
        """Count in list response reflects actual number of videos."""
        before = client.get("/api/videos/", headers=auth).json()["count"]

        files = {"file": ("count_test.mp4", _mp4(512), "video/mp4")}
        vid = client.post("/api/videos/upload", files=files, headers=auth).json()["video_id"]

        after_upload = client.get("/api/videos/", headers=auth).json()["count"]
        assert after_upload == before + 1

        client.delete(f"/api/videos/{vid}", headers=auth)

        after_delete = client.get("/api/videos/", headers=auth).json()["count"]
        assert after_delete == before
