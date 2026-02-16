"""Keyword extraction and tracking service"""
from sklearn.feature_extraction.text import TfidfVectorizer
import logging
from typing import List, Optional
from app.models.schemas import KeywordData, KeywordContext, TranscriptionSegment
import re

logger = logging.getLogger(__name__)


class KeywordTracker:
    """Service for extracting and tracking keywords"""
    
    def __init__(self):
        """Initialize keyword tracker"""
        self.vectorizer = TfidfVectorizer(
            max_features=100,
            stop_words='english',
            ngram_range=(1, 2),  # Unigrams and bigrams
            min_df=1
        )
    
    async def extract_keywords(
        self, 
        text: str, 
        top_n: int = 20,
        segments: Optional[List[TranscriptionSegment]] = None
    ) -> List[KeywordData]:
        """
        Extract keywords using TF-IDF algorithm
        
        Args:
            text: Full transcription text
            top_n: Number of top keywords to extract
            segments: Optional list of transcription segments for timestamp tracking
            
        Returns:
            List of KeywordData with keywords, scores, and timestamps
        """
        try:
            if not text or len(text.strip()) == 0:
                return []
            
            # Split text into sentences for TF-IDF
            sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
            
            if len(sentences) < 2:
                # Not enough text for TF-IDF, return empty
                return []
            
            # Fit and transform
            tfidf_matrix = self.vectorizer.fit_transform(sentences)
            feature_names = self.vectorizer.get_feature_names_out()
            
            # Get average TF-IDF scores for each term
            avg_scores = tfidf_matrix.mean(axis=0).A1
            
            # Get top keywords
            top_indices = avg_scores.argsort()[-top_n:][::-1]
            
            keywords = []
            for idx in top_indices:
                keyword = feature_names[idx]
                score = float(avg_scores[idx])
                
                # Find timestamps and contexts for this keyword
                timestamps, contexts = self._find_keyword_occurrences(
                    keyword, 
                    segments if segments else []
                )
                
                keyword_data = KeywordData(
                    word=keyword,
                    count=len(timestamps),
                    timestamps=timestamps,
                    avg_sentiment=0.0,  # Will be calculated later
                    contexts=contexts
                )
                keywords.append(keyword_data)
            
            logger.info(f"Extracted {len(keywords)} keywords")
            return keywords
            
        except Exception as e:
            logger.error(f"Keyword extraction failed: {str(e)}")
            return []
    
    async def track_custom_keywords(
        self, 
        keywords: List[str],
        segments: List[TranscriptionSegment]
    ) -> List[KeywordData]:
        """
        Track specific custom keywords in transcription
        
        Args:
            keywords: List of keywords to track
            segments: List of transcription segments
            
        Returns:
            List of KeywordData for tracked keywords
        """
        results = []
        
        for keyword in keywords:
            timestamps, contexts = self._find_keyword_occurrences(keyword, segments)
            
            if timestamps:  # Only include if keyword was found
                keyword_data = KeywordData(
                    word=keyword,
                    count=len(timestamps),
                    timestamps=timestamps,
                    avg_sentiment=0.0,
                    contexts=contexts
                )
                results.append(keyword_data)
        
        logger.info(f"Tracked {len(results)} custom keywords")
        return results
    
    def _find_keyword_occurrences(
        self, 
        keyword: str,
        segments: List[TranscriptionSegment]
    ) -> tuple[List[float], List[KeywordContext]]:
        """
        Find all occurrences of a keyword in segments
        
        Args:
            keyword: Keyword to find
            segments: List of transcription segments
            
        Returns:
            Tuple of (timestamps, contexts)
        """
        timestamps = []
        contexts = []
        
        # Create case-insensitive pattern
        pattern = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
        
        for segment in segments:
            if pattern.search(segment.text):
                timestamps.append(segment.start)
                
                # Get context (the segment text itself)
                context = KeywordContext(
                    timestamp=segment.start,
                    text=segment.text
                )
                contexts.append(context)
        
        return timestamps, contexts
    
    async def get_context(
        self,
        keyword: str,
        timestamp: float,
        segments: List[TranscriptionSegment],
        window: float = 5.0
    ) -> str:
        """
        Get context window around a keyword occurrence
        
        Args:
            keyword: The keyword
            timestamp: Timestamp of the occurrence
            segments: List of transcription segments
            window: Time window in seconds (±window)
            
        Returns:
            Context text
        """
        # Find segments within the time window
        context_segments = [
            seg for seg in segments
            if abs(seg.start - timestamp) <= window
        ]
        
        # Sort by timestamp
        context_segments.sort(key=lambda x: x.start)
        
        # Combine text
        context_text = " ".join(seg.text for seg in context_segments)
        
        return context_text
    
    async def calculate_keyword_sentiment(
        self,
        keywords: List[KeywordData],
        segments: List[TranscriptionSegment]
    ) -> List[KeywordData]:
        """
        Calculate average sentiment for each keyword based on context
        
        Args:
            keywords: List of keyword data
            segments: List of transcription segments with sentiment
            
        Returns:
            Updated keyword data with sentiment scores
        """
        from app.services.sentiment_analyzer import SentimentAnalyzer
        
        analyzer = SentimentAnalyzer()
        
        for keyword in keywords:
            if not keyword.contexts:
                continue
            
            # Analyze sentiment of each context
            sentiments = []
            for context in keyword.contexts:
                result = await analyzer.analyze(context.text)
                sentiments.append(result.score)
            
            # Calculate average
            if sentiments:
                keyword.avg_sentiment = sum(sentiments) / len(sentiments)
        
        return keywords
    
    async def merge_keywords(
        self,
        auto_keywords: List[KeywordData],
        custom_keywords: List[KeywordData]
    ) -> List[KeywordData]:
        """
        Merge auto-extracted and custom keywords, removing duplicates
        
        Args:
            auto_keywords: Keywords extracted via TF-IDF
            custom_keywords: User-specified keywords
            
        Returns:
            Merged list of keywords
        """
        # Create a dictionary to track keywords by word
        keyword_dict = {}
        
        # Add auto keywords
        for kw in auto_keywords:
            keyword_dict[kw.word.lower()] = kw
        
        # Add or update with custom keywords
        for kw in custom_keywords:
            key = kw.word.lower()
            if key in keyword_dict:
                # Merge timestamps and contexts
                existing = keyword_dict[key]
                existing.timestamps.extend(kw.timestamps)
                existing.contexts.extend(kw.contexts)
                existing.count = len(existing.timestamps)
            else:
                keyword_dict[key] = kw
        
        # Convert back to list and sort by count
        merged = list(keyword_dict.values())
        merged.sort(key=lambda x: x.count, reverse=True)
        
        return merged
