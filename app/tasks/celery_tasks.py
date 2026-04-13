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
        
        # Step 2.5 - Translate if Tamil detected
        logger.info("Step 2.5: Checking language and translating if needed...")
        from app.services.translator import translator
        
        detected_language = transcription.language
        logger.info(f"Detected language: {detected_language}")
        
        # If Tamil (ta) is detected, translate to English
        if detected_language == "ta":
            logger.info("Tamil language detected. Translating to English...")
            try:
                translated_segments = asyncio.run(translator.translate_segments(
                    transcription.segments,
                    source_language="ta",
                    target_language="en"
                ))
                
                # Update transcription with translated segments
                # Keep original for reference
                for i, seg in enumerate(translated_segments):
                    seg.original_text = transcription.segments[i].text
                    seg.original_language = "ta"
                    seg.translated_language = "en"
                
                transcription.segments = translated_segments
                logger.info("Translation completed successfully")
            except Exception as translate_error:
                logger.warning(f"Translation failed, continuing with original Tamil text: {str(translate_error)}")
                # Continue with original Tamil text if translation fails
        
        # Step 3 - Analyze sentiment
        logger.info("Step 3: Analyzing sentiment...")
        sentiment_analyzer = SentimentAnalyzer()
        timeline = asyncio.run(sentiment_analyzer._create_timeline_async(transcription.segments))
        
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


@celery_app.task(name="generate_clips_task")
def generate_clips_task(
    job_id: str,
    video_id: str,
    user_id: str,
    dataset_content: str,  # base64-encoded bytes (Celery JSON serialization)
    dataset_filename: str,
    similarity_threshold: float = 0.5,
) -> None:
    """
    Orchestrate the full clip-highlights pipeline:
    1. Update job status → processing
    2. Locate video file and load transcript segments from analysis JSON
    3. Parse dataset content
    4. Run semantic matching
    5. Extract clips, upload to Firebase Storage, write Clip_Result to Firestore
    6. Update job status → completed (or failed on unrecoverable error)

    Args:
        job_id: Clip job ID (UUID)
        video_id: ID of the video to process
        user_id: ID of the user who initiated the job
        dataset_content: Base64-encoded dataset file bytes
        dataset_filename: Original filename (used to detect format)
        similarity_threshold: Minimum similarity score for a match (default 0.5)
    """
    import base64
    import glob
    import json
    import os
    import shutil
    import tempfile
    import uuid
    from pathlib import Path

    from app.services.clip_extractor import ClipExtractor, ClipExtractionError
    from app.services.dataset_parser import DatasetParser
    from app.services.firebase_service import firebase_service
    from app.services.semantic_matcher import SemanticMatcher

    # Resolve the uploads directory relative to this file
    backend_dir = Path(__file__).parent.parent.parent
    uploads_dir = backend_dir / "uploads"

    try:
        # Step 1 — mark job as processing
        asyncio.run(firebase_service.update_clip_job(job_id, {"status": "processing"}))

        # Step 2 — locate video file
        video_pattern = str(uploads_dir / f"{video_id}_*")
        video_extensions = (".mp4", ".avi", ".mov", ".mkv")
        candidates = [
            f for f in glob.glob(video_pattern)
            if any(f.lower().endswith(ext) for ext in video_extensions)
        ]
        if not candidates:
            raise FileNotFoundError(f"Video file not found for video_id: {video_id}")
        video_path = candidates[0]

        # Step 3 — load transcript segments from analysis JSON
        analysis_path = uploads_dir / f"{video_id}_analysis.json"
        if not analysis_path.exists():
            raise FileNotFoundError(f"Analysis JSON not found: {analysis_path}")

        with open(analysis_path, "r", encoding="utf-8") as f:
            analysis_json = json.load(f)

        # Segments are stored under the "timeline" key
        raw_segments = analysis_json.get("timeline", [])
        if not raw_segments:
            logger.warning(f"No timeline segments found for video_id: {video_id}")

        # Normalise segments to the shape SemanticMatcher expects:
        # { text, start, end, original_language, translated_text }
        segments: list[Dict[str, Any]] = []
        for i, seg in enumerate(raw_segments):
            start = float(seg.get("timestamp", 0.0))
            duration = float(seg.get("duration", 0.0))
            # Derive end from next segment's timestamp when available
            if i + 1 < len(raw_segments):
                end = float(raw_segments[i + 1].get("timestamp", start + duration))
            else:
                end = start + duration

            segments.append({
                "text": seg.get("text", ""),
                "start": start,
                "end": end,
                "original_language": seg.get("original_language", ""),
                "translated_text": seg.get("translated_text", ""),
            })

        # Determine video duration from last segment end
        video_duration = segments[-1]["end"] if segments else 0.0

        # Step 4 — parse dataset
        raw_bytes = base64.b64decode(dataset_content)
        parser = DatasetParser()
        dataset_entries = parser.parse(raw_bytes, dataset_filename)

        # Step 5 — semantic matching
        matcher = SemanticMatcher()
        matches = matcher.match(dataset_entries, segments, threshold=similarity_threshold)

        # Step 6 — extract clips, upload, write Clip_Result
        extractor = ClipExtractor()
        tmp_dir = tempfile.mkdtemp(prefix="clips_")
        clip_ids: list[str] = []

        try:
            for match in matches:
                clip_id = str(uuid.uuid4())
                seg = match.segment
                start = float(seg["start"])
                end = float(seg["end"])
                output_path = os.path.join(tmp_dir, f"{clip_id}.mp4")
                storage_path = f"clips/{video_id}/{clip_id}.mp4"

                try:
                    extractor.extract(
                        video_path=video_path,
                        start=start,
                        end=end,
                        output_path=output_path,
                        video_duration=video_duration,
                    )
                except ClipExtractionError as clip_err:
                    logger.error(
                        "Skipping clip for segment [%.2f, %.2f]: %s",
                        start, end, str(clip_err),
                    )
                    continue

                # Upload to Firebase Storage
                asyncio.run(firebase_service.upload_file(output_path, storage_path))

                # Write Clip_Result to Firestore
                clip_result = {
                    "clip_id": clip_id,
                    "video_id": video_id,
                    "job_id": job_id,
                    "start_time": start,
                    "end_time": end,
                    "matched_text": seg.get("text", ""),
                    "dataset_entry": match.dataset_entry,
                    "similarity_score": match.similarity_score,
                    "storage_path": storage_path,
                }
                asyncio.run(firebase_service.create_clip_result(clip_result))
                clip_ids.append(clip_id)

                # Clean up temp clip file
                try:
                    os.remove(output_path)
                except OSError:
                    pass

        finally:
            # Clean up temp directory
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # Step 7 — mark job completed
        asyncio.run(firebase_service.update_clip_job(
            job_id,
            {"status": "completed", "clip_ids": clip_ids},
        ))
        logger.info(
            "generate_clips_task completed for job_id=%s, %d clips produced",
            job_id, len(clip_ids),
        )

    except Exception as e:
        logger.error(
            "generate_clips_task failed for job_id=%s video_id=%s: %s",
            job_id, video_id, str(e),
        )
        # Step 8 — mark job failed with error message
        try:
            asyncio.run(firebase_service.update_clip_job(
                job_id,
                {"status": "failed", "error": str(e)},
            ))
        except Exception as update_err:
            logger.error("Failed to update clip job status to failed: %s", str(update_err))


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


@celery_app.task(bind=True, max_retries=3)
def process_video_local_task(self, video_id: str, video_path: str) -> Dict[str, Any]:
    """
    Process a video locally (development mode)
    
    Args:
        video_id: ID of the video to process
        video_path: Local path to the video file
        
    Returns:
        Dictionary with processing results
    """
    import os
    import json
    import subprocess
    from pathlib import Path
    import shutil
    import time
    
    try:
        logger.info(f"Starting local video processing for video_id: {video_id}")
        
        # Get the project root directory (parent of backend)
        backend_dir = Path(__file__).parent.parent.parent
        project_root = backend_dir.parent
        
        logger.info(f"Project root: {project_root}")
        logger.info(f"Video path: {video_path}")
        
        # Update status to processing
        videos_file = project_root / 'backend' / 'uploads' / 'videos.json'
        if videos_file.exists():
            try:
                with open(videos_file, 'r') as f:
                    videos = json.load(f)
                
                for video in videos:
                    if video['video_id'] == video_id:
                        video['status'] = 'processing'
                        break
                
                with open(videos_file, 'w') as f:
                    json.dump(videos, f, indent=2)
                logger.info(f"Updated video {video_id} status to processing")
            except Exception as e:
                logger.warning(f"Could not update status to processing: {str(e)}")
        
        # Run the local analyzer script with timeout
        logger.info(f"Running local analyzer for {video_id}...")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                ['python', 'local_video_analyzer.py', video_path],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=3600  # 1 hour timeout
            )
            
            elapsed = time.time() - start_time
            logger.info(f"Local analyzer completed in {elapsed:.1f}s for video_id: {video_id}")
            
            if result.returncode != 0:
                logger.error(f"Local analyzer stderr: {result.stderr}")
                raise RuntimeError(f"Local analyzer failed: {result.stderr}")
            
            logger.info(f"Analyzer output: {result.stdout}")
            
        except subprocess.TimeoutExpired:
            logger.error(f"Local analyzer timed out after 1 hour for video_id: {video_id}")
            raise RuntimeError("Video processing timed out - file may be too large")
        
        # Copy analysis file to backend uploads
        local_results_dir = project_root / 'local_results'
        backend_uploads_dir = project_root / 'backend' / 'uploads'
        
        logger.info(f"Looking for analysis files in: {local_results_dir}")
        logger.info(f"Target directory: {backend_uploads_dir}")
        
        # Find the analysis file
        analysis_files = list(local_results_dir.glob(f'{video_id}*_analysis.json'))
        logger.info(f"Found {len(analysis_files)} analysis files")
        
        if analysis_files:
            source_file = analysis_files[0]
            dest_file = backend_uploads_dir / f'{video_id}_analysis.json'
            logger.info(f"Copying from {source_file} to {dest_file}")
            
            try:
                shutil.copy(source_file, dest_file)
                logger.info(f"✅ File copied successfully")
            except Exception as copy_error:
                logger.error(f"❌ File copy failed: {str(copy_error)}", exc_info=True)
                raise
        else:
            logger.error(f"❌ Analysis file not found in {local_results_dir}")
            # List all files in the directory for debugging
            all_files = list(local_results_dir.glob('*'))
            logger.error(f"Files in directory: {[f.name for f in all_files]}")
            raise RuntimeError("Analysis file not found after processing")
        
        # Update video status to completed
        logger.info(f"Updating status in: {videos_file}")
        
        if videos_file.exists():
            try:
                with open(videos_file, 'r') as f:
                    videos = json.load(f)
                
                logger.info(f"Loaded {len(videos)} videos from JSON")
                
                # Update status
                updated = False
                for video in videos:
                    if video['video_id'] == video_id:
                        video['status'] = 'completed'
                        updated = True
                        logger.info(f"✅ Updated video {video_id} status to completed")
                        break
                
                if not updated:
                    logger.warning(f"⚠️  Video {video_id} not found in videos.json")
                
                with open(videos_file, 'w') as f:
                    json.dump(videos, f, indent=2)
                
                logger.info(f"✅ Saved updated videos.json")
            except Exception as json_error:
                logger.error(f"❌ Failed to update videos.json: {str(json_error)}", exc_info=True)
                raise
        else:
            logger.error(f"❌ videos.json not found at {videos_file}")
        
        logger.info(f"Video processing completed for video_id: {video_id}")
        
        return {
            'video_id': video_id,
            'status': 'completed',
            'message': 'Video processed successfully'
        }
        
    except Exception as e:
        logger.error(f"Local video processing failed for video_id {video_id}: {str(e)}")
        
        # Update status to failed
        try:
            backend_dir = Path(__file__).parent.parent.parent
            project_root = backend_dir.parent
            videos_file = project_root / 'backend' / 'uploads' / 'videos.json'
            
            if videos_file.exists():
                with open(videos_file, 'r') as f:
                    videos = json.load(f)
                
                for video in videos:
                    if video['video_id'] == video_id:
                        video['status'] = 'failed'
                        video['error'] = str(e)
                        break
                
                with open(videos_file, 'w') as f:
                    json.dump(videos, f, indent=2)
        except Exception as update_error:
            logger.error(f"Failed to update video status: {str(update_error)}")
        
        # Retry if not max retries
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying video processing (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=60)
        
        return {
            'video_id': video_id,
            'status': 'failed',
            'error': str(e)
        }
