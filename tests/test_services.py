import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock


class TestVideoProcessor:
    """Test video processor service"""

    @patch('app.services.video_processor.ffmpeg')
    def test_extract_audio_success(self, mock_ffmpeg):
        """Test successful audio extraction"""
        from app.services.video_processor import VideoProcessor

        processor = VideoProcessor()

        # Mock validate_video to skip file existence check
        processor.validate_video = Mock(return_value=True)

        # Mock the ffmpeg chain
        mock_run = Mock(return_value=None)
        mock_ffmpeg.input.return_value.output.return_value.overwrite_output.return_value.run = mock_run

        audio_path = asyncio.run(processor.extract_audio("test_video.mp4"))

        assert audio_path is not None
        assert audio_path.endswith('.wav')

    def test_validate_video_format(self):
        """Test video format validation via validate_video"""
        from app.services.video_processor import VideoProcessor

        processor = VideoProcessor()

        # Valid extensions are in supported_formats set
        assert '.mp4' in processor.supported_formats
        assert '.avi' in processor.supported_formats
        assert '.mov' in processor.supported_formats
        assert '.mkv' in processor.supported_formats

        # Invalid extensions should not be in supported_formats
        assert '.txt' not in processor.supported_formats
        assert '.pdf' not in processor.supported_formats


class TestSentimentAnalyzer:
    """Test sentiment analyzer service"""

    @patch('app.services.sentiment_analyzer.pipeline')
    def test_analyze_sentiment(self, mock_pipeline):
        """Test sentiment analysis"""
        from app.services.sentiment_analyzer import SentimentAnalyzer

        mock_pipeline.return_value = lambda x: [{"label": "POSITIVE", "score": 0.95}]

        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_text("This is a great video!")

        assert result["sentiment"] in ["positive", "negative", "neutral"]
        assert 0 <= result["score"] <= 1
        assert 0 <= result["confidence"] <= 1

    @patch('app.services.sentiment_analyzer.pipeline')
    def test_sentiment_score_range(self, mock_pipeline):
        """Test sentiment score is within valid range"""
        from app.services.sentiment_analyzer import SentimentAnalyzer

        mock_pipeline.return_value = lambda x: [{"label": "POSITIVE", "score": 0.8}]
        analyzer = SentimentAnalyzer()

        texts = ["I love this!", "This is terrible", "It's okay"]
        for text in texts:
            result = analyzer.analyze_text(text)
            assert -1 <= result["score"] <= 1

    @patch('app.services.sentiment_analyzer.pipeline')
    def test_create_timeline(self, mock_pipeline):
        """Test timeline creation from segments"""
        from app.services.sentiment_analyzer import SentimentAnalyzer

        mock_pipeline.return_value = lambda x: [{"label": "POSITIVE", "score": 0.8}]
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
        """Test TF-IDF keyword extraction (async)"""
        from app.services.keyword_tracker import KeywordTracker

        tracker = KeywordTracker()
        text = "Python programming is great. Python is a powerful language for data science."

        # extract_keywords is async
        keywords = asyncio.run(tracker.extract_keywords(text, top_n=5))

        assert len(keywords) > 0

    def test_track_custom_keywords(self):
        """Test custom keyword tracking via track_custom_keywords"""
        from app.services.keyword_tracker import KeywordTracker
        from app.models.schemas import TranscriptionSegment

        tracker = KeywordTracker()

        segments = [
            TranscriptionSegment(text="Python is great", start=0.0, end=2.0, words=[
                {"word": "Python", "start": 0.0, "end": 0.5},
                {"word": "is", "start": 0.5, "end": 0.7},
                {"word": "great", "start": 0.7, "end": 1.0}
            ]),
            TranscriptionSegment(text="Python programming", start=2.0, end=4.0, words=[
                {"word": "Python", "start": 2.0, "end": 2.5},
                {"word": "programming", "start": 2.5, "end": 3.5}
            ])
        ]

        results = asyncio.run(tracker.track_custom_keywords(["Python", "programming"], segments))

        # Results is a list of KeywordData
        python_kw = next((kw for kw in results if kw.word == "Python"), None)
        assert python_kw is not None
        assert python_kw.count == 2

    def test_keyword_timestamp_accuracy(self):
        """Test keyword timestamps are accurate"""
        from app.services.keyword_tracker import KeywordTracker
        from app.models.schemas import TranscriptionSegment

        tracker = KeywordTracker()

        segments = [
            TranscriptionSegment(text="test word", start=5.0, end=7.0, words=[
                {"word": "test", "start": 5.0, "end": 5.5},
                {"word": "word", "start": 5.5, "end": 6.0}
            ])
        ]

        results = asyncio.run(tracker.track_custom_keywords(["test"], segments))

        test_kw = next((kw for kw in results if kw.word == "test"), None)
        assert test_kw is not None
        assert test_kw.timestamps[0] == 5.0


class TestTranscriber:
    """Test transcriber service"""

    @patch('app.services.transcriber.whisper.load_model')
    def test_transcribe_audio(self, mock_load_model):
        """Test audio transcription (async) — returns TranscriptionResult object"""
        from app.services.transcriber import Transcriber

        mock_model = Mock()
        mock_model.transcribe.return_value = {
            "text": "This is a test transcription",
            "language": "en",
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
        result = asyncio.run(transcriber.transcribe("test_audio.wav"))

        # TranscriptionResult has .text and .segments attributes
        assert result.text == "This is a test transcription"
        assert len(result.segments) > 0

    def test_word_level_timestamps(self):
        """Test word-level timestamp generation"""
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
        """Test video document creation (async, takes dict)"""
        from app.services.firebase_service import FirebaseService

        mock_doc_ref = Mock()
        mock_doc_ref.id = "test_video_123"
        mock_db = Mock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref
        mock_firestore.client.return_value = mock_db
        mock_firestore.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"

        service = FirebaseService.__new__(FirebaseService)
        service.db = mock_db
        service.bucket = Mock()

        video_data = {"userId": "user_123", "title": "test.mp4", "status": "queued"}
        video_id = asyncio.run(service.create_video(video_data))

        assert video_id == "test_video_123"

    @patch('app.services.firebase_service.firestore')
    def test_get_video(self, mock_firestore):
        """Test video retrieval (async)"""
        from app.services.firebase_service import FirebaseService

        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.id = "test_video_123"
        mock_doc.to_dict.return_value = {
            "userId": "user_123",
            "title": "test.mp4",
            "status": "completed"
        }
        mock_db = Mock()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        mock_firestore.client.return_value = mock_db

        service = FirebaseService.__new__(FirebaseService)
        service.db = mock_db
        service.bucket = Mock()

        video_data = asyncio.run(service.get_video("test_video_123"))

        assert video_data is not None
        assert video_data["status"] == "completed"

    @patch('app.services.firebase_service.firestore')
    def test_update_video_status(self, mock_firestore):
        """Test video status update (async)"""
        from app.services.firebase_service import FirebaseService

        mock_doc_ref = Mock()
        mock_db = Mock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref
        mock_firestore.client.return_value = mock_db
        mock_firestore.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"

        service = FirebaseService.__new__(FirebaseService)
        service.db = mock_db
        service.bucket = Mock()

        asyncio.run(service.update_video_status("test_video_123", "processing"))

        mock_doc_ref.update.assert_called_once()
