"""Video upload and management API routes"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from typing import Dict, Any
import os
import tempfile
import logging
from app.services.firebase_service import firebase_service
from app.api.dependencies import verify_auth_token
from app.models.schemas import VideoUploadResponse, StreamStartRequest, StreamStartResponse
from app.config import settings
from app.utils.helpers import generate_id

logger = logging.getLogger(__name__)

router = APIRouter()

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
        
        # Create temporary file to save uploaded content
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        try:
            # Upload to Firebase Storage
            storage_path = f"videos/{user_id}/{video_id}/{file.filename}"
            storage_url = await firebase_service.upload_file(temp_file_path, storage_path)
            
            # Create video document in Firestore
            video_data = {
                'title': file.filename,
                'type': 'pre-recorded',
                'url': storage_url,
                'status': 'queued',
                'duration': 0,  # Will be updated after processing
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
            
            return VideoUploadResponse(
                video_id=created_video_id,
                status="queued",
                message="Video uploaded successfully and queued for processing"
            )
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload video: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload video"
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
        
        # Create video document in Firestore
        video_data = {
            'title': request.title,
            'type': 'live-stream',
            'url': request.stream_url,
            'status': 'processing',
            'duration': 0,
            'userId': user_id
        }
        
        created_video_id = await firebase_service.create_video(video_data)
        
        # TODO: Start stream processing (will be implemented in Task 11)
        
        # Generate WebSocket URL
        ws_url = f"ws://localhost:8000/ws/analysis/{created_video_id}"
        
        logger.info(f"Live stream started: {created_video_id}")
        
        return StreamStartResponse(
            video_id=created_video_id,
            status="processing",
            websocket_url=ws_url
        )
        
    except Exception as e:
        logger.error(f"Failed to start stream: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start live stream processing"
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
        # Verify video exists and belongs to user
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
        
        # TODO: Stop stream processing (will be implemented in Task 11)
        
        # Update video status
        await firebase_service.update_video_status(video_id, "completed")
        
        logger.info(f"Live stream stopped: {video_id}")
        
        return {"message": "Stream stopped successfully", "video_id": video_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop stream: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop stream"
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
        videos = await firebase_service.get_videos_by_user(user_info['uid'])
        return {"videos": videos, "count": len(videos)}
        
    except Exception as e:
        logger.error(f"Failed to list videos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve videos"
        )
