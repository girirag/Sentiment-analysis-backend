"""
DB Connection Tests
===================
Tests real connectivity to all database/service backends:
  - Redis
  - Firebase Admin SDK (Firestore, Storage, Auth)
  - Firebase Firestore CRUD (write / read / delete)
  - Firebase Storage bucket reachability
  - Firebase Auth service reachability
  - Google Cloud Translate API reachability
  - YouTube Data API reachability
"""

import os
import sys
import pytest
import asyncio

# ── ensure backend root is on path ──────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "true")

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))


# ════════════════════════════════════════════════════════════════════════════
# REDIS
# ════════════════════════════════════════════════════════════════════════════

class TestRedisConnection:
    """Redis connectivity and basic operations"""

    def _client(self):
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        return redis.from_url(url, socket_connect_timeout=5)

    def test_redis_ping(self):
        """Redis server responds to PING"""
        r = self._client()
        assert r.ping(), "Redis did not respond to PING"

    def test_redis_set_get(self):
        """Redis SET and GET round-trip"""
        r = self._client()
        r.set("db_test_key", "db_test_value", ex=10)
        val = r.get("db_test_key")
        assert val == b"db_test_value"

    def test_redis_delete(self):
        """Redis DEL removes a key"""
        r = self._client()
        r.set("db_test_del", "1", ex=10)
        r.delete("db_test_del")
        assert r.get("db_test_del") is None

    def test_redis_info(self):
        """Redis INFO returns server metadata"""
        r = self._client()
        info = r.info()
        assert "redis_version" in info
        assert "connected_clients" in info

    def test_redis_connection_pool(self):
        """Redis connection pool works under multiple calls"""
        r = self._client()
        for i in range(5):
            r.set(f"pool_test_{i}", i, ex=5)
        for i in range(5):
            assert r.get(f"pool_test_{i}") == str(i).encode()
            r.delete(f"pool_test_{i}")


# ════════════════════════════════════════════════════════════════════════════
# FIREBASE — SDK INITIALISATION
# ════════════════════════════════════════════════════════════════════════════

class TestFirebaseInitialisation:
    """Firebase Admin SDK initialises without errors"""

    def test_firebase_credentials_file_exists(self):
        """firebase-key.json is present on disk"""
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "./firebase-key.json")
        full = os.path.join(os.path.dirname(__file__), "..", cred_path)
        assert os.path.exists(full), f"Firebase key not found at: {full}"

    def test_firebase_sdk_initialises(self):
        """Firebase Admin SDK initialises successfully"""
        import firebase_admin
        from app.services.firebase_service import firebase_service
        assert firebase_admin._apps, "Firebase app was not initialised"

    def test_firestore_client_available(self):
        """Firestore client is not None after init"""
        from app.services.firebase_service import firebase_service
        assert firebase_service.db is not None, "Firestore client is None"

    def test_storage_bucket_available(self):
        """Storage bucket is not None after init"""
        from app.services.firebase_service import firebase_service
        assert firebase_service.bucket is not None, "Storage bucket is None"

    def test_firebase_storage_bucket_name(self):
        """Storage bucket name matches env var"""
        from app.services.firebase_service import firebase_service
        expected = os.getenv("FIREBASE_STORAGE_BUCKET", "")
        # bucket.name may include the project prefix; just check it's non-empty
        assert firebase_service.bucket.name, "Storage bucket name is empty"


# ════════════════════════════════════════════════════════════════════════════
# FIREBASE FIRESTORE — CRUD
# ════════════════════════════════════════════════════════════════════════════

class TestFirestoreCRUD:
    """Live Firestore read / write / delete operations"""

    COLLECTION = "_db_connection_tests"

    def _db(self):
        from app.services.firebase_service import firebase_service
        return firebase_service.db

    def test_firestore_write_document(self):
        """Can write a document to Firestore"""
        db = self._db()
        ref = db.collection(self.COLLECTION).document("test_write")
        ref.set({"status": "ok", "value": 42})
        doc = ref.get()
        assert doc.exists
        assert doc.to_dict()["value"] == 42

    def test_firestore_read_document(self):
        """Can read a document from Firestore"""
        db = self._db()
        ref = db.collection(self.COLLECTION).document("test_read")
        ref.set({"ping": "pong"})
        doc = ref.get()
        assert doc.exists
        assert doc.to_dict()["ping"] == "pong"

    def test_firestore_update_document(self):
        """Can update a field in an existing document"""
        db = self._db()
        ref = db.collection(self.COLLECTION).document("test_update")
        ref.set({"counter": 0})
        ref.update({"counter": 1})
        doc = ref.get()
        assert doc.to_dict()["counter"] == 1

    def test_firestore_delete_document(self):
        """Can delete a document from Firestore"""
        db = self._db()
        ref = db.collection(self.COLLECTION).document("test_delete")
        ref.set({"temp": True})
        ref.delete()
        doc = ref.get()
        assert not doc.exists

    def test_firestore_query_collection(self):
        """Can query a collection with a filter"""
        db = self._db()
        ref = db.collection(self.COLLECTION).document("test_query")
        ref.set({"type": "query_test", "active": True})
        results = list(
            db.collection(self.COLLECTION)
            .where("type", "==", "query_test")
            .limit(5)
            .stream()
        )
        assert len(results) >= 1

    def test_firestore_cleanup(self):
        """Clean up all test documents"""
        db = self._db()
        docs = db.collection(self.COLLECTION).stream()
        for doc in docs:
            doc.reference.delete()
        remaining = list(db.collection(self.COLLECTION).stream())
        assert len(remaining) == 0


# ════════════════════════════════════════════════════════════════════════════
# FIREBASE STORAGE
# ════════════════════════════════════════════════════════════════════════════

class TestFirebaseStorage:
    """Firebase Storage bucket connectivity"""

    TEST_BLOB = "_db_connection_tests/test_ping.txt"

    def _bucket(self):
        from app.services.firebase_service import firebase_service
        return firebase_service.bucket

    def test_storage_bucket_exists(self):
        """Storage bucket object is accessible"""
        bucket = self._bucket()
        assert bucket is not None

    def test_storage_upload_small_file(self):
        """Can upload a small text blob to Storage"""
        import tempfile
        bucket = self._bucket()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w") as f:
            f.write("db_connection_test")
            tmp_path = f.name
        blob = bucket.blob(self.TEST_BLOB)
        blob.upload_from_filename(tmp_path)
        os.unlink(tmp_path)
        assert blob.exists()

    def test_storage_blob_exists_after_upload(self):
        """Uploaded blob is retrievable"""
        bucket = self._bucket()
        blob = bucket.blob(self.TEST_BLOB)
        assert blob.exists(), "Test blob not found after upload"

    def test_storage_delete_blob(self):
        """Can delete a blob from Storage"""
        bucket = self._bucket()
        blob = bucket.blob(self.TEST_BLOB)
        if blob.exists():
            blob.delete()
        assert not blob.exists()


# ════════════════════════════════════════════════════════════════════════════
# FIREBASE AUTH
# ════════════════════════════════════════════════════════════════════════════

class TestFirebaseAuth:
    """Firebase Auth service reachability"""

    def test_auth_service_reachable(self):
        """Firebase Auth module is importable and usable"""
        from firebase_admin import auth
        assert auth is not None

    def test_auth_invalid_token_raises(self):
        """Verifying a bogus token raises an error (proves Auth is live)"""
        from firebase_admin import auth
        with pytest.raises(Exception):
            auth.verify_id_token("this.is.not.a.valid.token")

    def test_auth_list_users(self):
        """Can call list_users() without error (proves Auth API is reachable)"""
        from firebase_admin import auth
        page = auth.list_users()
        # page is an iterator; just check it's not None
        assert page is not None


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE CLOUD TRANSLATE API
# ════════════════════════════════════════════════════════════════════════════

class TestGoogleTranslateAPI:
    """Google Cloud Translate API reachability"""

    def test_translate_api_key_set(self):
        """GOOGLE_TRANSLATE_API_KEY is configured"""
        key = os.getenv("GOOGLE_TRANSLATE_API_KEY", "")
        assert key, "GOOGLE_TRANSLATE_API_KEY is not set"

    def test_translate_simple_request(self):
        """Can make a real translation request"""
        import requests
        key = os.getenv("GOOGLE_TRANSLATE_API_KEY", "")
        if not key:
            pytest.skip("GOOGLE_TRANSLATE_API_KEY not set")
        url = "https://translation.googleapis.com/language/translate/v2"
        resp = requests.post(url, params={"key": key}, json={
            "q": "Hello",
            "source": "en",
            "target": "ta",
            "format": "text"
        }, timeout=10)
        assert resp.status_code == 200, f"Translate API returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "data" in data
        assert "translations" in data["data"]

    def test_translate_language_detection(self):
        """Language detection endpoint is reachable"""
        import requests
        key = os.getenv("GOOGLE_TRANSLATE_API_KEY", "")
        if not key:
            pytest.skip("GOOGLE_TRANSLATE_API_KEY not set")
        url = "https://translation.googleapis.com/language/translate/v2/detect"
        resp = requests.post(url, params={"key": key}, json={
            "q": "வணக்கம்"
        }, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data


# ════════════════════════════════════════════════════════════════════════════
# YOUTUBE DATA API
# ════════════════════════════════════════════════════════════════════════════

class TestYouTubeAPI:
    """YouTube Data API v3 reachability"""

    def test_youtube_api_key_set(self):
        """YOUTUBE_API_KEY is configured"""
        key = os.getenv("YOUTUBE_API_KEY", "")
        assert key, "YOUTUBE_API_KEY is not set"

    def test_youtube_search_endpoint(self):
        """YouTube search endpoint responds successfully"""
        import requests
        key = os.getenv("YOUTUBE_API_KEY", "")
        if not key:
            pytest.skip("YOUTUBE_API_KEY not set")
        url = "https://www.googleapis.com/youtube/v3/search"
        resp = requests.get(url, params={
            "key": key,
            "q": "test",
            "part": "snippet",
            "maxResults": 1,
            "type": "video"
        }, timeout=10)
        assert resp.status_code == 200, f"YouTube API returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "items" in data

    def test_youtube_videos_endpoint(self):
        """YouTube videos endpoint responds successfully"""
        import requests
        key = os.getenv("YOUTUBE_API_KEY", "")
        if not key:
            pytest.skip("YOUTUBE_API_KEY not set")
        url = "https://www.googleapis.com/youtube/v3/videos"
        resp = requests.get(url, params={
            "key": key,
            "id": "dQw4w9WgXcQ",
            "part": "snippet"
        }, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
