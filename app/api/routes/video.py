"""Video upload and management API routes"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from typing import Dict, Any
import os
import tempfile
import logging
import json
from datetime import datetime
from app.services.firebase_service import firebase_service
from app.api.dependencies import verify_auth_token
from app.models.schemas import VideoUploadResponse, StreamStartRequest, StreamStartResponse
from app.config import settings
from app.utils.helpers import generate_id

logger = logging.getLogger(__name__)

router = APIRouter()

# Import Celery tasks (with error handling for circular imports)
try:
    from app.tasks.celery_tasks import process_video_local_task
    CELERY_AVAILABLE = True
    logger.info("Celery tasks imported successfully")
except Exception as e:
    CELERY_AVAILABLE = False
    logger.warning(f"Celery tasks not available: {str(e)}")

# Supported video formats
SUPPORTED_FORMATS = {'.mp4', '.avi', '.mov', '.mkv'}
MAX_SIZE_BYTES = settings.max_video_size_mb * 1024 * 1024


def validate_video_format(filename: str) -> bool:
    """Validate if the video format is supported"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in SUPPORTED_FORMATS


def validate_video_size(file_size: int) -> bool:
    """Validate if the video size is within limits"""
    return file_size <= MAX_SIZE_BYTES


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Upload a pre-recorded video for sentiment analysis
    
    Args:
        file: Video file to upload
        user_info: Authenticated user information
        
    Returns:
        VideoUploadResponse with video_id and status
        
    Raises:
        HTTPException: If validation fails or upload errors occur
    """
    try:
        # Validate file format
        if not validate_video_format(file.filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video format not supported. Supported formats: {', '.join(SUPPORTED_FORMATS)}"
            )
        
        # Read file to check size
        file_content = await file.read()
        file_size = len(file_content)
        
        # Validate file size
        if not validate_video_size(file_size):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video file size exceeds maximum limit of {settings.max_video_size_mb}MB"
            )
        
        # Generate unique video ID
        video_id = generate_id()
        user_id = user_info['uid']
        
        # Create uploads directory if it doesn't exist
        uploads_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Save file locally
        file_path = os.path.join(uploads_dir, f"{video_id}_{file.filename}")
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        try:
            # Development mode: Store in local JSON file
            if settings.environment == "development":
                logger.info(f"Development mode: Storing video metadata locally for {video_id}")
                
                # Load existing videos
                videos_file = os.path.join(uploads_dir, "videos.json")
                videos = []
                if os.path.exists(videos_file):
                    with open(videos_file, "r") as f:
                        videos = json.load(f)
                
                # Add new video (initially queued)
                video_data = {
                    'video_id': video_id,
                    'title': file.filename,
                    'type': 'pre-recorded',
                    'url': file_path,
                    'status': 'queued',
                    'duration': 0,
                    'userId': user_id,
                    'filename': file.filename,
                    'size': file_size,
                    'created_at': datetime.now().isoformat()
                }
                videos.append(video_data)
                
                # Save videos
                with open(videos_file, "w") as f:
                    json.dump(videos, f, indent=2)
                
                logger.info(f"Video uploaded successfully (dev mode): {video_id}")
                
                # Automatically start processing
                if CELERY_AVAILABLE:
                    try:
                        logger.info(f"Attempting to trigger automatic processing for {video_id}")
                        task = process_video_local_task.delay(video_id, file_path)
                        logger.info(f"Celery task triggered successfully: {task.id}")
                        
                        # Update status to processing
                        video_data['status'] = 'processing'
                        with open(videos_file, "w") as f:
                            json.dump(videos, f, indent=2)
                        
                        status_msg = "processing"
                    except Exception as celery_error:
                        logger.error(f"Failed to trigger Celery task: {str(celery_error)}", exc_info=True)
                        status_msg = "queued"
                else:
                    logger.warning("Celery not available, video queued for manual processing")
                    status_msg = "queued"
                
                return VideoUploadResponse(
                    video_id=video_id,
                    status=status_msg,
                    message=f"Video uploaded successfully and {'processing started automatically' if status_msg == 'processing' else 'queued for processing'}"
                )
            
            # Production mode: Upload to Firebase Storage
            storage_path = f"videos/{user_id}/{video_id}/{file.filename}"
            storage_url = await firebase_service.upload_file(file_path, storage_path)
            
            # Create video document in Firestore
            video_data = {
                'title': file.filename,
                'type': 'pre-recorded',
                'url': storage_url,
                'status': 'queued',
                'duration': 0,
                'userId': user_id,
                'filename': file.filename,
                'size': file_size,
                'storagePath': storage_path
            }
            
            created_video_id = await firebase_service.create_video(video_data)
            
            # Queue Celery task for processing
            from app.tasks.celery_tasks import process_video_task
            process_video_task.delay(created_video_id, user_id)
            
            logger.info(f"Video uploaded successfully: {created_video_id}")
            
            # Clean up local file in production
            if os.path.exists(file_path):
                os.remove(file_path)
            
            return VideoUploadResponse(
                video_id=created_video_id,
                status="queued",
                message="Video uploaded successfully and queued for processing"
            )
            
        except Exception as e:
            # Clean up file on error
            if os.path.exists(file_path):
                os.remove(file_path)
            raise
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload video: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video: {str(e)}"
        )


@router.post("/stream/start", response_model=StreamStartResponse)
async def start_stream(
    request: StreamStartRequest,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Start processing a live video stream
    
    Args:
        request: Stream URL and title
        user_info: Authenticated user information
        
    Returns:
        StreamStartResponse with video_id and WebSocket URL
    """
    try:
        # Generate unique video ID
        video_id = generate_id()
        user_id = user_info['uid']
        
        logger.info(f"Starting stream for user {user_id}: {request.title}")
        
        # Development mode: Store locally
        if settings.environment == "development":
            uploads_dir = os.path.join(os.getcwd(), "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            videos_file = os.path.join(uploads_dir, "videos.json")
            
            # Load existing videos
            videos = []
            if os.path.exists(videos_file):
                try:
                    with open(videos_file, "r") as f:
                        videos = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading videos.json: {str(e)}")
                    videos = []
            
            # Add new stream
            video_data = {
                'video_id': video_id,
                'title': request.title,
                'type': 'live-stream',
                'url': request.stream_url,
                'status': 'streaming',
                'duration': 0,
                'userId': user_id,
                'created_at': datetime.now().isoformat(),
                'stream_data': {
                    'chunks_processed': 0,
                    'started_at': datetime.now().isoformat()
                }
            }
            videos.append(video_data)
            
            # Save videos
            try:
                with open(videos_file, "w") as f:
                    json.dump(videos, f, indent=2)
                logger.info(f"Saved stream metadata for {video_id}")
            except Exception as e:
                logger.error(f"Error saving videos.json: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to save stream metadata: {str(e)}"
                )
            
            # Note: Stream processing will be started in background
            # For now, just return success and let the WebSocket handle updates
            
            logger.info(f"Live stream started (dev mode): {video_id}")
            
            # Generate WebSocket URL
            ws_url = f"ws://localhost:8000/ws/stream/{video_id}"
            
            return StreamStartResponse(
                video_id=video_id,
                status="streaming",
                websocket_url=ws_url
            )
        
        # Production mode: Use Firebase
        video_data = {
            'title': request.title,
            'type': 'live-stream',
            'url': request.stream_url,
            'status': 'streaming',
            'duration': 0,
            'userId': user_id
        }
        
        created_video_id = await firebase_service.create_video(video_data)
        
        # Generate WebSocket URL
        ws_url = f"ws://localhost:8000/ws/stream/{created_video_id}"
        
        logger.info(f"Live stream started: {created_video_id}")
        
        return StreamStartResponse(
            video_id=created_video_id,
            status="streaming",
            websocket_url=ws_url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start stream: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start live stream: {str(e)}"
        )


@router.post("/stream/stop/{video_id}")
async def stop_stream(
    video_id: str,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Stop processing a live video stream
    
    Args:
        video_id: ID of the video/stream to stop
        user_info: Authenticated user information
        
    Returns:
        Success message
    """
    try:
        # Development mode
        if settings.environment == "development":
            uploads_dir = os.path.join(os.getcwd(), "uploads")
            videos_file = os.path.join(uploads_dir, "videos.json")
            
            if not os.path.exists(videos_file):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
            
            with open(videos_file, "r") as f:
                videos = json.load(f)
            
            # Find video
            video = next((v for v in videos if v['video_id'] == video_id), None)
            
            if not video:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
            
            # Verify ownership
            if video['userId'] != user_info['uid']:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to stop this stream"
                )
            
            # Stop stream processor
            if hasattr(start_stream, 'active_streams') and video_id in start_stream.active_streams:
                stream_processor = start_stream.active_streams[video_id]
                stream_processor.stop()
                
                # Save final stream data
                chunks_processed = stream_processor.get_chunk_count()
                
                # Update video status
                video['status'] = 'completed'
                video['stream_data']['chunks_processed'] = chunks_processed
                video['stream_data']['stopped_at'] = datetime.now().isoformat()
                
                with open(videos_file, "w") as f:
                    json.dump(videos, f, indent=2)
                
                # Clean up
                del start_stream.active_streams[video_id]
                
                logger.info(f"Live stream stopped (dev mode): {video_id}, processed {chunks_processed} chunks")
            else:
                # Stream not found in active streams, just update status
                video['status'] = 'completed'
                with open(videos_file, "w") as f:
                    json.dump(videos, f, indent=2)
            
            return {
                "message": "Stream stopped successfully",
                "video_id": video_id,
                "chunks_processed": video.get('stream_data', {}).get('chunks_processed', 0)
            }
        
        # Production mode
        video = await firebase_service.get_video(video_id)
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        if video['userId'] != user_info['uid']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to stop this stream"
            )
        
        # TODO: Stop stream processing
        
        # Update video status
        await firebase_service.update_video_status(video_id, "completed")
        
        logger.info(f"Live stream stopped: {video_id}")
        
        return {"message": "Stream stopped successfully", "video_id": video_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop stream: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop stream: {str(e)}"
        )


@router.get("/{video_id}")
async def get_video(
    video_id: str,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get video details
    
    Args:
        video_id: ID of the video
        user_info: Authenticated user information
        
    Returns:
        Video details
    """
    try:
        # Development mode: Read from local JSON
        if settings.environment == "development":
            uploads_dir = os.path.join(os.getcwd(), "uploads")
            videos_file = os.path.join(uploads_dir, "videos.json")
            
            if os.path.exists(videos_file):
                with open(videos_file, "r") as f:
                    videos = json.load(f)
                
                # Find video
                video = next((v for v in videos if v['video_id'] == video_id), None)
                
                if not video:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Video not found"
                    )
                
                # Verify ownership
                if video['userId'] != user_info['uid']:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to access this video"
                    )
                
                return video
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
        
        # Production mode: Read from Firebase
        video = await firebase_service.get_video(video_id)
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Verify ownership
        if video['userId'] != user_info['uid']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this video"
            )
        
        return video
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get video: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve video"
        )


@router.post("/process/{video_id}")
async def process_video(
    video_id: str,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Manually trigger video processing
    
    Args:
        video_id: ID of the video to process
        user_info: Authenticated user information
        
    Returns:
        Processing status
    """
    try:
        # Development mode: Process locally
        if settings.environment == "development":
            uploads_dir = os.path.join(os.getcwd(), "uploads")
            videos_file = os.path.join(uploads_dir, "videos.json")
            
            if not os.path.exists(videos_file):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
            
            with open(videos_file, "r") as f:
                videos = json.load(f)
            
            # Find video
            video = next((v for v in videos if v['video_id'] == video_id), None)
            
            if not video:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
            
            # Verify ownership
            if video['userId'] != user_info['uid']:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to process this video"
                )
            
            # Update status to processing
            video['status'] = 'processing'
            with open(videos_file, "w") as f:
                json.dump(videos, f, indent=2)
            
            # Start processing in background
            if not CELERY_AVAILABLE:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Background processing service not available"
                )
            
            task = process_video_local_task.delay(video_id, video['url'])
            
            logger.info(f"Video processing started (dev mode): {video_id}")
            
            return {
                "video_id": video_id,
                "status": "processing",
                "message": "Video processing started"
            }
        
        # Production mode: Use Celery
        video = await firebase_service.get_video(video_id)
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Verify ownership
        if video['userId'] != user_info['uid']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to process this video"
            )
        
        # Queue Celery task for processing
        from app.tasks.celery_tasks import process_video_task
        process_video_task.delay(video_id, user_info['uid'])
        
        # Update status
        await firebase_service.update_video_status(video_id, "processing")
        
        logger.info(f"Video processing started: {video_id}")
        
        return {
            "video_id": video_id,
            "status": "processing",
            "message": "Video processing started"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process video: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start video processing: {str(e)}"
        )


@router.delete("/{video_id}")
async def delete_video(
    video_id: str,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Delete a video and its associated files
    
    Args:
        video_id: ID of the video to delete
        user_info: Authenticated user information
        
    Returns:
        Success message
    """
    try:
        # Development mode: Delete from local storage
        if settings.environment == "development":
            uploads_dir = os.path.join(os.getcwd(), "uploads")
            videos_file = os.path.join(uploads_dir, "videos.json")
            
            if not os.path.exists(videos_file):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
            
            with open(videos_file, "r") as f:
                videos = json.load(f)
            
            # Find video
            video = next((v for v in videos if v['video_id'] == video_id), None)
            
            if not video:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
            
            # Verify ownership
            if video['userId'] != user_info['uid']:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to delete this video"
                )
            
            # Delete video file
            video_path = video.get('url')
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                    logger.info(f"Deleted video file: {video_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete video file: {str(e)}")
            
            # Delete analysis file
            analysis_path = os.path.join(uploads_dir, f"{video_id}_analysis.json")
            if os.path.exists(analysis_path):
                try:
                    os.remove(analysis_path)
                    logger.info(f"Deleted analysis file: {analysis_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete analysis file: {str(e)}")
            
            # Remove from videos list
            videos = [v for v in videos if v['video_id'] != video_id]
            
            # Save updated list
            with open(videos_file, "w") as f:
                json.dump(videos, f, indent=2)
            
            logger.info(f"Video deleted successfully (dev mode): {video_id}")
            
            return {
                "success": True,
                "message": "Video deleted successfully",
                "video_id": video_id
            }
        
        # Production mode: Delete from Firebase
        video = await firebase_service.get_video(video_id)
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        # Verify ownership
        if video['userId'] != user_info['uid']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this video"
            )
        
        # Delete from Firebase Storage
        if 'storagePath' in video:
            try:
                await firebase_service.delete_file(video['storagePath'])
            except Exception as e:
                logger.warning(f"Failed to delete file from storage: {str(e)}")
        
        # Delete video document
        await firebase_service.delete_video(video_id)
        
        # Delete associated analysis
        try:
            await firebase_service.delete_analysis_by_video(video_id)
        except Exception as e:
            logger.warning(f"Failed to delete analysis: {str(e)}")
        
        logger.info(f"Video deleted successfully: {video_id}")
        
        return {
            "success": True,
            "message": "Video deleted successfully",
            "video_id": video_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete video: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete video: {str(e)}"
        )


@router.get("/")
async def list_videos(
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    List all videos for the authenticated user
    
    Args:
        user_info: Authenticated user information
        
    Returns:
        List of videos
    """
    try:
        # Development mode: Read from local JSON
        if settings.environment == "development":
            uploads_dir = os.path.join(os.getcwd(), "uploads")
            videos_file = os.path.join(uploads_dir, "videos.json")
            
            if os.path.exists(videos_file):
                with open(videos_file, "r") as f:
                    all_videos = json.load(f)
                # Filter by user
                videos = [v for v in all_videos if v.get('userId') == user_info['uid']]
                return {"videos": videos, "count": len(videos)}
            else:
                return {"videos": [], "count": 0}
        
        # Production mode: Read from Firebase
        videos = await firebase_service.get_videos_by_user(user_info['uid'])
        return {"videos": videos, "count": len(videos)}
        
    except Exception as e:
        logger.error(f"Failed to list videos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve videos"
        )
