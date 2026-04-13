"""Sentiment analysis service using transformer models"""
from transformers import pipeline
import logging
from typing import List
from app.models.schemas import SentimentResult, TranscriptionSegment, TimelinePoint
from app.config import settings

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Service for analyzing sentiment using transformer models"""
    
    def __init__(self, model_name: str = None):
        """
        Initialize sentiment analyzer
        
        Args:
            model_name: Transformer model name (default from settings)
        """
        self.model_name = model_name or settings.sentiment_model
        self.pipeline = None
        self._load_model()
    
    def _load_model(self):
        """Load sentiment analysis model"""
        try:
            logger.info(f"Loading sentiment model: {self.model_name}")
            self.pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                return_all_scores=True
            )
            logger.info("Sentiment model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load sentiment model: {str(e)}")
            raise
    
    def _normalize_score(self, label: str, score: float) -> float:
        """
        Normalize sentiment score to range [-1, 1]
        
        Args:
            label: Sentiment label (POSITIVE, NEGATIVE, NEUTRAL)
            score: Confidence score [0, 1]
            
        Returns:
            Normalized score [-1, 1]
        """
        if label == "POSITIVE":
            return score
        elif label == "NEGATIVE":
            return -score
        else:  # NEUTRAL
            return 0.0
    
    def _classify_sentiment(self, score: float) -> str:
        """
        Classify sentiment based on score
        
        Args:
            score: Sentiment score [-1, 1]
            
        Returns:
            Sentiment classification (positive, negative, neutral)
        """
        if score > 0.1:
            return "positive"
        elif score < -0.1:
            return "negative"
        else:
            return "neutral"
    
    async def analyze(self, text: str) -> SentimentResult:
        """
        Analyze sentiment of a text segment
        
        Args:
            text: Text to analyze
            
        Returns:
            SentimentResult with sentiment, score, and confidence
        """
        try:
            if not text or len(text.strip()) == 0:
                # Return neutral for empty text
                return SentimentResult(
                    sentiment="neutral",
                    score=0.0,
                    confidence=1.0,
                    timestamp=0.0
                )
            
            # Get sentiment predictions
            results = self.pipeline(text[:512])[0]  # Limit to 512 chars for model
            
            # Find the prediction with highest score
            best_prediction = max(results, key=lambda x: x['score'])
            label = best_prediction['label']
            confidence = best_prediction['score']
            
            # Normalize score to [-1, 1]
            normalized_score = self._normalize_score(label, confidence)
            
            # Classify sentiment
            sentiment = self._classify_sentiment(normalized_score)
            
            return SentimentResult(
                sentiment=sentiment,
                score=normalized_score,
                confidence=confidence,
                timestamp=0.0
            )
            
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {str(e)}")
            # Return neutral on error
            return SentimentResult(
                sentiment="neutral",
                score=0.0,
                confidence=0.0,
                timestamp=0.0
            )
    
    async def analyze_segments(self, segments: List[TranscriptionSegment]) -> List[SentimentResult]:
        """
        Analyze sentiment for multiple transcription segments in a single batch.
        """
        if not segments:
            return []

        texts = [seg.text[:512] if seg.text and seg.text.strip() else " " for seg in segments]

        try:
            # Run entire batch in one pipeline call
            batch_results = self.pipeline(texts, batch_size=32, truncation=True)
        except Exception as e:
            logger.error(f"Batch sentiment analysis failed: {e}")
            batch_results = [None] * len(texts)

        results = []
        for seg, preds in zip(segments, batch_results):
            if preds is None:
                results.append(SentimentResult(sentiment="neutral", score=0.0, confidence=0.0, timestamp=seg.start))
                continue
            best = max(preds, key=lambda x: x["score"])
            norm = self._normalize_score(best["label"], best["score"])
            results.append(SentimentResult(
                sentiment=self._classify_sentiment(norm),
                score=norm,
                confidence=best["score"],
                timestamp=seg.start,
            ))
        return results
    
    async def _create_timeline_async(
        self,
        segments: List[TranscriptionSegment],
        window_duration: float = 10.0
    ) -> List[TimelinePoint]:
        """
        Create sentiment timeline with fixed time windows using a single batch call.
        """
        if not segments:
            return []

        window_duration = max(5.0, min(10.0, window_duration))
        max_time = max(seg.end for seg in segments)

        # Build all windows first
        windows = []
        t = 0.0
        while t < max_time:
            window_end = t + window_duration
            window_segs = [s for s in segments if s.start < window_end and s.end > t]
            text = " ".join(s.text for s in window_segs).strip() if window_segs else ""
            windows.append((t, text))
            t = window_end

        # Batch-analyse all non-empty windows in one pipeline call
        texts = [text[:512] if text else " " for _, text in windows]
        try:
            batch_results = self.pipeline(texts, batch_size=32, truncation=True)
        except Exception as e:
            logger.error(f"Batch timeline sentiment failed: {e}")
            batch_results = [None] * len(texts)

        timeline = []
        for (timestamp, _), preds in zip(windows, batch_results):
            if preds is None:
                timeline.append(TimelinePoint(timestamp=timestamp, sentiment="neutral", score=0.0))
                continue
            best = max(preds, key=lambda x: x["score"])
            norm = self._normalize_score(best["label"], best["score"])
            timeline.append(TimelinePoint(
                timestamp=timestamp,
                sentiment=self._classify_sentiment(norm),
                score=norm,
            ))

        return timeline
    
    def analyze_text(self, text: str) -> dict:
        """
        Synchronous wrapper around analyze() for testing and simple use cases.

        Returns:
            dict with keys: sentiment, score, confidence
        """
        import asyncio
        result = asyncio.run(self.analyze(text))
        return {
            "sentiment": result.sentiment,
            "score": result.score,
            "confidence": result.confidence,
        }

    def create_timeline(self, segments: list, window_duration: float = 10.0):
        """
        Accepts either plain dicts (sync test usage) or TranscriptionSegment objects.
        Runs the async pipeline synchronously.
        """
        import asyncio
        from app.models.schemas import TranscriptionSegment

        seg_objs = []
        for s in segments:
            if isinstance(s, TranscriptionSegment):
                seg_objs.append(s)
            else:
                seg_objs.append(TranscriptionSegment(text=s["text"], start=s["start"], end=s["end"]))

        async def _run():
            return await self._create_timeline_async(seg_objs, window_duration)

        timeline = asyncio.run(_run())
        return [{"timestamp": p.timestamp, "sentiment": p.sentiment, "score": p.score} for p in timeline]


        """
        Calculate summary statistics from timeline
        
        Args:
            timeline: List of timeline points
            
        Returns:
            Dictionary with summary statistics
        """
        if not timeline:
            return {
                'overall_sentiment': 'neutral',
                'avg_score': 0.0,
                'positive_percentage': 0.0,
                'negative_percentage': 0.0,
                'neutral_percentage': 0.0
            }
        
        # Count sentiments
        positive_count = sum(1 for point in timeline if point.sentiment == 'positive')
        negative_count = sum(1 for point in timeline if point.sentiment == 'negative')
        neutral_count = sum(1 for point in timeline if point.sentiment == 'neutral')
        total = len(timeline)
        
        # Calculate average score
        avg_score = sum(point.score for point in timeline) / total
        
        # Determine overall sentiment
        if avg_score > 0.1:
            overall_sentiment = 'positive'
        elif avg_score < -0.1:
            overall_sentiment = 'negative'
        else:
            overall_sentiment = 'neutral'
        
        return {
            'overall_sentiment': overall_sentiment,
            'avg_score': avg_score,
            'positive_percentage': (positive_count / total) * 100,
            'negative_percentage': (negative_count / total) * 100,
            'neutral_percentage': (neutral_count / total) * 100
        }
