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
        Analyze sentiment for multiple transcription segments
        
        Args:
            segments: List of transcription segments
            
        Returns:
            List of sentiment results
        """
        results = []
        
        for segment in segments:
            result = await self.analyze(segment.text)
            result.timestamp = segment.start
            results.append(result)
        
        return results
    
    async def create_timeline(
        self, 
        segments: List[TranscriptionSegment],
        window_duration: float = 10.0
    ) -> List[TimelinePoint]:
        """
        Create sentiment timeline with fixed time windows
        
        Args:
            segments: List of transcription segments
            window_duration: Duration of each time window in seconds (5-10 seconds)
            
        Returns:
            List of timeline points
        """
        if not segments:
            return []
        
        # Ensure window duration is between 5 and 10 seconds
        window_duration = max(5.0, min(10.0, window_duration))
        
        # Get total duration
        max_time = max(seg.end for seg in segments)
        
        # Create time windows
        timeline = []
        current_time = 0.0
        
        while current_time < max_time:
            window_end = current_time + window_duration
            
            # Find segments in this window
            window_segments = [
                seg for seg in segments
                if seg.start < window_end and seg.end > current_time
            ]
            
            if window_segments:
                # Combine text from all segments in window
                combined_text = " ".join(seg.text for seg in window_segments)
                
                # Analyze sentiment
                result = await self.analyze(combined_text)
                
                timeline.append(TimelinePoint(
                    timestamp=current_time,
                    sentiment=result.sentiment,
                    score=result.score
                ))
            else:
                # No segments in this window, use neutral
                timeline.append(TimelinePoint(
                    timestamp=current_time,
                    sentiment="neutral",
                    score=0.0
                ))
            
            current_time = window_end
        
        return timeline
    
    def calculate_summary(self, timeline: List[TimelinePoint]) -> dict:
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
