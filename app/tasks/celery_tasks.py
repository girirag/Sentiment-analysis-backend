"""Celery tasks for background video processing"""
from celery import Celery
from app.config import settings
import logging
import asyncio
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery(
    'video_sentiment_analysis',
    broker=settings.redis_url,
    backend=settings.redis_url
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

logger.info("Celery app initialized")


@celery_app.task(bind=True, max_retries=3)
def process_video_task(self, video_id: str, user_id: str) -> Dict[str, Any]:
    """
    Process a video: extract audio, transcribe, analyze sentiment, extract keywords
    
    Args:
        video_id: ID of the video to process
        user_id: ID of the user who owns the video
        
    Returns:
        Dictionary with processing results
    """
    from app.services.firebase_service import firebase_service
    from app.services.video_processor import VideoProcessor
    from app.services.transcriber import Transcriber
    from app.services.sentiment_analyzer import SentimentAnalyzer
    from app.services.keyword_tracker import KeywordTracker
    from app.models.schemas import AnalysisSummary
    
    try:
        logger.info(f"Starting video processing for video_id: {video_id}")
        
        # Update status to processing
        asyncio.run(firebase_service.update_video_status(video_id, "processing"))
        
        # Get video details
        video = asyncio.run(firebase_service.get_video(video_id))
        if not video:
            raise ValueError(f"Video not found: {video_id}")
        
        # Step 1 - Extract audio
        logger.info("Step 1: Extracting audio...")
        video_processor = VideoProcessor()
        audio_path = asyncio.run(video_processor.extract_audio(video['url']))
        
        # Step 2 - Transcribe audio
        logger.info("Step 2: Transcribing audio...")
        transcriber = Transcriber()
        transcription = asyncio.run(transcriber.transcribe_with_retry(audio_path))
        
        # Step 3 - Analyze sentiment
        logger.info("Step 3: Analyzing sentiment...")
        sentiment_analyzer = SentimentAnalyzer()
        timeline = asyncio.run(sentiment_analyzer.create_timeline(transcription.segments))
        
        # Step 4 - Extract keywords
        logger.info("Step 4: Extracting keywords...")
        keyword_tracker = KeywordTracker()
        keywords = asyncio.run(keyword_tracker.extract_keywords(
            transcription.text,
            segments=transcription.segments
        ))
        
        # Calculate keyword sentiments
        keywords = asyncio.run(keyword_tracker.calculate_keyword_sentiment(
            keywords,
            transcription.segments
        ))
        
        # Step 5 - Calculate summary
        logger.info("Step 5: Calculating summary...")
        summary_stats = sentiment_analyzer.calculate_summary(timeline)
        
        # Get video duration
        duration = video.get('duration', 0)
        if duration == 0 and timeline:
            duration = timeline[-1].timestamp
        
        summary = AnalysisSummary(
            overall_sentiment=summary_stats['overall_sentiment'],
            avg_score=summary_stats['avg_score'],
            total_keywords=len(keywords),
            duration=duration,
            positive_percentage=summary_stats['positive_percentage'],
            negative_percentage=summary_stats['negative_percentage'],
            neutral_percentage=summary_stats['neutral_percentage']
        )
        
        # Step 6 - Store analysis results
        logger.info("Step 6: Storing analysis results...")
        analysis_data = {
            'videoId': video_id,
            'transcription': [seg.dict() for seg in transcription.segments],
            'keywords': [kw.dict() for kw in keywords],
            'timeline': [point.dict() for point in timeline],
            'summary': summary.dict()
        }
        analysis_id = asyncio.run(firebase_service.create_analysis(analysis_data))
        
        # Update video status to completed
        asyncio.run(firebase_service.update_video_status(video_id, "completed"))
        
        # Clean up audio file
        import os
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        logger.info(f"Video processing completed for video_id: {video_id}")
        
        return {
            'video_id': video_id,
            'analysis_id': analysis_id,
            'status': 'completed',
            'message': 'Video processed successfully'
        }
        
    except Exception as e:
        logger.error(f"Video processing failed for video_id {video_id}: {str(e)}")
        
        # Update status to failed
        try:
            asyncio.run(firebase_service.update_video_status(
                video_id, 
                "failed", 
                error=str(e)
            ))
        except Exception as update_error:
            logger.error(f"Failed to update video status: {str(update_error)}")
        
        # Retry if not max retries
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)  # Retry after 60 seconds
        
        return {
            'video_id': video_id,
            'status': 'failed',
            'error': str(e)
        }


@celery_app.task
def process_stream_chunk(video_id: str, audio_chunk: bytes, chunk_index: int) -> Dict[str, Any]:
    """
    Process a chunk of live stream audio
    
    Args:
        video_id: ID of the video/stream
        audio_chunk: Audio data bytes
        chunk_index: Index of the chunk
        
    Returns:
        Dictionary with chunk processing results
    """
    try:
        logger.info(f"Processing stream chunk {chunk_index} for video_id: {video_id}")
        
        # TODO: Implement chunk processing (will be implemented in Task 11)
        # 1. Transcribe chunk
        # 2. Analyze sentiment
        # 3. Extract keywords
        # 4. Send results via WebSocket
        
        return {
            'video_id': video_id,
            'chunk_index': chunk_index,
            'status': 'processed'
        }
        
    except Exception as e:
        logger.error(f"Stream chunk processing failed: {str(e)}")
        return {
            'video_id': video_id,
            'chunk_index': chunk_index,
            'status': 'failed',
            'error': str(e)
        }
