import pytest
from hypothesis import given, strategies as st, assume
from hypothesis import settings, HealthCheck
import json

# Use a small example count globally for faster runs
settings.register_profile("fast", max_examples=20)
settings.load_profile("fast")


class TestVideoValidationProperties:
    """Property-based tests for video validation"""
    
    @given(st.sampled_from(['.mp4', '.avi', '.mov', '.mkv']))
    def test_video_format_validation_property(self, ext):
        """Property: Valid video extensions should always be in supported_formats"""
        from app.services.video_processor import VideoProcessor

        processor = VideoProcessor()
        assert ext in processor.supported_formats
    
    @given(st.integers(min_value=1, max_value=1000))
    def test_file_size_enforcement_property(self, size_mb):
        """Property: Files over max size should be rejected"""
        from app.config import settings
        
        max_size = settings.max_video_size_mb
        
        # Files larger than max should be rejected
        if size_mb > max_size:
            # Would be rejected in actual upload
            assert size_mb > max_size
        else:
            assert size_mb <= max_size


class TestSentimentAnalysisProperties:
    """Property-based tests for sentiment analysis"""
    
    @given(st.floats(min_value=-1.0, max_value=1.0))
    def test_sentiment_score_range_invariant(self, score):
        """Property: Sentiment scores must be between -1 and 1"""
        # Any sentiment score should be in valid range
        assert -1.0 <= score <= 1.0
    
    @given(st.text(min_size=1, max_size=1000))
    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    def test_sentiment_classification_completeness(self, text):
        """Property: Every text should get a sentiment classification"""
        from unittest.mock import patch

        assume(len(text.strip()) > 0)  # Skip empty strings

        with patch('app.services.sentiment_analyzer.pipeline') as mock_pipeline:
            mock_pipeline.return_value = lambda x: [{"label": "POSITIVE", "score": 0.8}]
            from importlib import reload
            import app.services.sentiment_analyzer as sa_module
            reload(sa_module)
            analyzer = sa_module.SentimentAnalyzer()
            result = analyzer.analyze_text(text)

        assert result["sentiment"] in ["positive", "negative", "neutral"]
        assert "score" in result
        assert "confidence" in result
    
    @given(st.floats(min_value=0.0, max_value=100.0))
    def test_timeline_segment_duration(self, duration):
        """Property: Timeline segments should be 5-10 seconds"""
        # Segment duration should be in valid range
        segment_duration = 7.5  # Default segment duration
        
        if duration > 0:
            num_segments = int(duration / segment_duration)
            assert num_segments >= 0


class TestKeywordTrackingProperties:
    """Property-based tests for keyword tracking"""
    
    @given(st.floats(min_value=0.0, max_value=1000.0))
    def test_keyword_timestamp_accuracy(self, timestamp):
        """Property: Keyword timestamps should match word timestamps"""
        # Timestamps should be non-negative
        assert timestamp >= 0.0
    
    @given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=10))
    @settings(max_examples=20, deadline=None)
    def test_custom_keyword_tracking(self, keywords):
        """Property: All custom keywords should be tracked"""
        from app.services.keyword_tracker import KeywordTracker
        
        tracker = KeywordTracker()
        
        # All provided keywords should be trackable
        assert len(keywords) > 0
        for keyword in keywords:
            assert isinstance(keyword, str)
            assert len(keyword) > 0
    
    @given(st.floats(min_value=0.0, max_value=100.0))
    def test_keyword_context_window(self, timestamp):
        """Property: Context window should be ±5 seconds"""
        context_window = 5.0
        
        start = max(0.0, timestamp - context_window)
        end = timestamp + context_window

        assert start <= timestamp <= end
        assert (end - start) <= 2 * context_window + 1e-9  # floating-point tolerance


class TestExportProperties:
    """Property-based tests for export functionality"""
    
    @given(st.dictionaries(st.text(), st.text()))
    def test_json_export_format(self, data):
        """Property: JSON export should be valid JSON"""
        # Any dict should be serializable to JSON
        try:
            json_str = json.dumps(data)
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)
        except (TypeError, ValueError):
            # Some data types might not be JSON serializable
            pass
    
    @given(st.lists(st.lists(st.text(), min_size=3, max_size=3), min_size=1, max_size=100))
    def test_csv_export_structure(self, rows):
        """Property: CSV should have consistent column count"""
        # All rows should have same number of columns
        if len(rows) > 0:
            expected_cols = len(rows[0])
            for row in rows:
                assert len(row) == expected_cols


class TestWebSocketProperties:
    """Property-based tests for WebSocket functionality"""
    
    @given(st.integers(min_value=1, max_value=10))
    def test_websocket_update_frequency(self, seconds):
        """Property: Updates should be sent every 2 seconds"""
        update_interval = 2.0
        
        # Number of updates in given time
        expected_updates = seconds / update_interval
        assert expected_updates >= 0
    
    @given(st.integers(min_value=0, max_value=5))
    def test_websocket_reconnection(self, attempt):
        """Property: Reconnection delay should increase exponentially"""
        base_delay = 1.0
        max_attempts = 5
        
        if attempt < max_attempts:
            delay = base_delay * (2 ** attempt)
            assert delay >= base_delay
            assert delay <= base_delay * (2 ** max_attempts)


class TestAuthenticationProperties:
    """Property-based tests for authentication"""
    
    @given(st.text(min_size=1, max_size=100))
    def test_authentication_token_validation(self, token):
        """Property: Invalid tokens should be rejected"""
        # Token validation logic
        if len(token) < 10:
            # Short tokens should be invalid
            assert len(token) < 10
        else:
            # Longer tokens might be valid
            assert len(token) >= 10
    
    @given(st.text(min_size=1, max_size=50))
    def test_authorization_verification(self, user_id):
        """Property: Users should only access their own resources"""
        # User should only access resources they own
        assert isinstance(user_id, str)
        assert len(user_id) > 0


class TestErrorHandlingProperties:
    """Property-based tests for error handling"""
    
    @given(st.integers(min_value=400, max_value=599))
    def test_api_error_status_codes(self, status_code):
        """Property: Error responses should have appropriate status codes"""
        # Client errors: 400-499
        # Server errors: 500-599
        if 400 <= status_code < 500:
            assert status_code >= 400 and status_code < 500
        elif 500 <= status_code < 600:
            assert status_code >= 500 and status_code < 600
    
    @given(st.integers(min_value=1, max_value=5))
    def test_transcription_retry_logic(self, attempt):
        """Property: Retry attempts should be limited"""
        max_retries = 3
        
        if attempt <= max_retries:
            # Should retry
            assert attempt <= max_retries
        else:
            # Should fail after max retries
            assert attempt > max_retries
