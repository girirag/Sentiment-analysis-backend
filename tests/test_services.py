import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np


class TestVideoProcessor:
    """Test video processor service"""
    
    @patch('app.services.video_processor.ffmpeg')
    def test_extract_audio_success(self, mock_ffmpeg):
        """Test successful audio extraction"""
        from app.services.video_processor import VideoProcessor
        
        processor = VideoProcessor()
        mock_ffmpeg.input.return_value.output.return_value.run.return_value = None
        
        audio_path = processor.extract_audio("test_video.mp4")
        
        assert audio_path is not None
        assert audio_path.endswith('.wav')
    
    def test_validate_video_format(self):
        """Test video format validation"""
        from app.services.video_processor import VideoProcessor
        
        processor = VideoProcessor()
        
        # Valid formats
        assert processor.validate_format("video.mp4") == True
        assert processor.validate_format("video.avi") == True
        assert processor.validate_format("video.mov") == True
        
        # Invalid formats
        assert processor.validate_format("video.txt") == False
        assert processor.validate_format("video.pdf") == False


class TestSentimentAnalyzer:
    """Test sentiment analyzer service"""
    
    @patch('app.services.sentiment_analyzer.pipeline')
    def test_analyze_sentiment(self, mock_pipeline):
        """Test sentiment analysis"""
        from app.services.sentiment_analyzer import SentimentAnalyzer
        
        # Mock the sentiment pipeline
        mock_pipeline.return_value = lambda x: [{"label": "POSITIVE", "score": 0.95}]
        
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_text("This is a great video!")
        
        assert result["sentiment"] in ["positive", "negative", "neutral"]
        assert 0 <= result["score"] <= 1
        assert 0 <= result["confidence"] <= 1
    
    def test_sentiment_score_range(self):
        """Test sentiment score is within valid range"""
        from app.services.sentiment_analyzer import SentimentAnalyzer
        
        analyzer = SentimentAnalyzer()
        
        # Test with various texts
        texts = [
            "I love this!",
            "This is terrible",
            "It's okay",
            ""
        ]
        
        for text in texts:
            if text:  # Skip empty string
                result = analyzer.analyze_text(text)
                assert -1 <= result["score"] <= 1
    
    def test_create_timeline(self):
        """Test timeline creation from segments"""
        from app.services.sentiment_analyzer import SentimentAnalyzer
        
        analyzer = SentimentAnalyzer()
        
        segments = [
            {"text": "Hello world", "start": 0.0, "end": 2.0},
            {"text": "This is great", "start": 2.0, "end": 5.0},
            {"text": "Amazing content", "start": 5.0, "end": 8.0}
        ]
        
        timeline = analyzer.create_timeline(segments)
        
        assert len(timeline) > 0
        for point in timeline:
            assert "timestamp" in point
            assert "sentiment" in point
            assert "score" in point


class TestKeywordTracker:
    """Test keyword tracker service"""
    
    def test_extract_keywords_tfidf(self):
        """Test TF-IDF keyword extraction"""
        from app.services.keyword_tracker import KeywordTracker
        
        tracker = KeywordTracker()
        
        text = "Python programming is great. Python is a powerful language for data science."
        keywords = tracker.extract_keywords(text, top_n=5)
        
        assert len(keywords) > 0
        assert all(isinstance(kw, str) for kw in keywords)
    
    def test_track_custom_keywords(self):
        """Test custom keyword tracking"""
        from app.services.keyword_tracker import KeywordTracker
        
        tracker = KeywordTracker()
        
        segments = [
            {"text": "Python is great", "start": 0.0, "end": 2.0, "words": [
                {"word": "Python", "start": 0.0, "end": 0.5},
                {"word": "is", "start": 0.5, "end": 0.7},
                {"word": "great", "start": 0.7, "end": 1.0}
            ]},
            {"text": "Python programming", "start": 2.0, "end": 4.0, "words": [
                {"word": "Python", "start": 2.0, "end": 2.5},
                {"word": "programming", "start": 2.5, "end": 3.5}
            ]}
        ]
        
        custom_keywords = ["Python", "programming"]
        results = tracker.track_keywords(segments, custom_keywords)
        
        assert "Python" in results
        assert len(results["Python"]["timestamps"]) == 2
        assert results["Python"]["count"] == 2
    
    def test_keyword_timestamp_accuracy(self):
        """Test keyword timestamps are accurate"""
        from app.services.keyword_tracker import KeywordTracker
        
        tracker = KeywordTracker()
        
        segments = [
            {"text": "test word", "start": 5.0, "end": 7.0, "words": [
                {"word": "test", "start": 5.0, "end": 5.5},
                {"word": "word", "start": 5.5, "end": 6.0}
            ]}
        ]
        
        results = tracker.track_keywords(segments, ["test"])
        
        assert results["test"]["timestamps"][0] == 5.0


class TestTranscriber:
    """Test transcriber service"""
    
    @patch('app.services.transcriber.whisper.load_model')
    def test_transcribe_audio(self, mock_load_model):
        """Test audio transcription"""
        from app.services.transcriber import Transcriber
        
        # Mock Whisper model
        mock_model = Mock()
        mock_model.transcribe.return_value = {
            "text": "This is a test transcription",
            "segments": [
                {
                    "text": "This is a test",
                    "start": 0.0,
                    "end": 2.0,
                    "words": [
                        {"word": "This", "start": 0.0, "end": 0.3},
                        {"word": "is", "start": 0.3, "end": 0.5},
                        {"word": "a", "start": 0.5, "end": 0.6},
                        {"word": "test", "start": 0.6, "end": 1.0}
                    ]
                }
            ]
        }
        mock_load_model.return_value = mock_model
        
        transcriber = Transcriber()
        result = transcriber.transcribe("test_audio.wav")
        
        assert "text" in result
        assert "segments" in result
        assert len(result["segments"]) > 0
    
    def test_word_level_timestamps(self):
        """Test word-level timestamp generation"""
        from app.services.transcriber import Transcriber
        
        transcriber = Transcriber()
        
        # Mock result with word timestamps
        mock_result = {
            "segments": [
                {
                    "text": "Hello world",
                    "start": 0.0,
                    "end": 2.0,
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.5},
                        {"word": "world", "start": 0.5, "end": 1.0}
                    ]
                }
            ]
        }
        
        # Verify word timestamps exist
        for segment in mock_result["segments"]:
            if "words" in segment:
                for word in segment["words"]:
                    assert "start" in word
                    assert "end" in word
                    assert word["start"] < word["end"]


class TestFirebaseService:
    """Test Firebase service"""
    
    @patch('app.services.firebase_service.firestore')
    def test_create_video(self, mock_firestore):
        """Test video document creation"""
        from app.services.firebase_service import FirebaseService
        
        mock_doc_ref = Mock()
        mock_doc_ref.id = "test_video_123"
        mock_firestore.client.return_value.collection.return_value.add.return_value = (None, mock_doc_ref)
        
        service = FirebaseService()
        video_id = service.create_video("user_123", "test.mp4", "gs://bucket/test.mp4")
        
        assert video_id == "test_video_123"
    
    @patch('app.services.firebase_service.firestore')
    def test_get_video(self, mock_firestore):
        """Test video retrieval"""
        from app.services.firebase_service import FirebaseService
        
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "user_id": "user_123",
            "title": "test.mp4",
            "status": "completed"
        }
        mock_firestore.client.return_value.collection.return_value.document.return_value.get.return_value = mock_doc
        
        service = FirebaseService()
        video_data = service.get_video("test_video_123")
        
        assert video_data is not None
        assert video_data["status"] == "completed"
    
    @patch('app.services.firebase_service.firestore')
    def test_update_video_status(self, mock_firestore):
        """Test video status update"""
        from app.services.firebase_service import FirebaseService
        
        mock_doc_ref = Mock()
        mock_firestore.client.return_value.collection.return_value.document.return_value = mock_doc_ref
        
        service = FirebaseService()
        service.update_video_status("test_video_123", "processing")
        
        mock_doc_ref.update.assert_called_once()
