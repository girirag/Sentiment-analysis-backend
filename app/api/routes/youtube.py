"""YouTube API routes for fetching videos"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from typing import Dict, Any, List
import logging
import uuid
import os
from datetime import datetime
from app.services.youtube_service import youtube_service
from app.api.dependencies import verify_auth_token
from app.tasks.celery_tasks import process_video_local_task
import json

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search")
async def search_youtube_videos(
    query: str = Query("trending", description="Search query"),
    max_results: int = Query(10, ge=1, le=50, description="Maximum results"),
    order: str = Query("relevance", description="Sort order"),
    region: str = Query("US", description="Region code"),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Search YouTube for videos
    
    Args:
        query: Search query
        max_results: Maximum number of results (1-50)
        order: Sort order (relevance, date, rating, viewCount)
        region: Region code (US, GB, IN, etc.)
        user_info: Authenticated user information
        
    Returns:
        List of videos from YouTube
    """
    try:
        videos = youtube_service.search_videos(
            query=query,
            max_results=max_results,
            order=order,
            region_code=region
        )
        
        return {
            "success": True,
            "count": len(videos),
            "videos": videos
        }
        
    except Exception as e:
        logger.error(f"Failed to search YouTube videos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search YouTube for videos"
        )


@router.get("/trending")
async def get_trending_videos(
    max_results: int = Query(10, ge=1, le=50),
    region: str = Query("US"),
    category: str = Query(None),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get trending videos from YouTube
    
    Args:
        max_results: Maximum number of results
        region: Region code
        category: Video category ID (optional)
        user_info: Authenticated user information
        
    Returns:
        List of trending videos
    """
    try:
        videos = youtube_service.get_trending_videos(
            max_results=max_results,
            region_code=region,
            category_id=category
        )
        
        return {
            "success": True,
            "count": len(videos),
            "videos": videos
        }
        
    except Exception as e:
        logger.error(f"Failed to get trending videos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get trending videos"
        )


@router.get("/channel/{channel_id}")
async def get_channel_videos(
    channel_id: str,
    max_results: int = Query(10, ge=1, le=50),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get videos from a specific YouTube channel
    
    Args:
        channel_id: YouTube channel ID
        max_results: Maximum number of results
        user_info: Authenticated user information
        
    Returns:
        List of videos from the channel
    """
    try:
        videos = youtube_service.get_channel_videos(
            channel_id=channel_id,
            max_results=max_results
        )
        
        return {
            "success": True,
            "channel_id": channel_id,
            "count": len(videos),
            "videos": videos
        }
        
    except Exception as e:
        logger.error(f"Failed to get channel videos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get videos from channel"
        )


@router.post("/import/{video_id}")
async def import_youtube_video(
    video_id: str,
    background_tasks: BackgroundTasks,
    auto_process: bool = Query(True, description="Automatically process video"),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Import a video from YouTube and optionally process it
    
    Args:
        video_id: YouTube video ID
        background_tasks: FastAPI background tasks
        auto_process: Whether to automatically process the video
        user_info: Authenticated user information
        
    Returns:
        Video import status
    """
    try:
        # Generate unique video ID
        import_video_id = str(uuid.uuid4())
        
        # Get backend directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        uploads_dir = os.path.join(backend_dir, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Create filename
        filename = f"{import_video_id}_youtube_{video_id}.mp4"
        file_path = os.path.join(uploads_dir, filename)
        
        # Download video
        success = youtube_service.download_video(video_id, file_path)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to download video from YouTube"
            )
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Get video info
        videos = youtube_service.search_videos(query=video_id, max_results=1)
        video_data = videos[0] if videos else {}
        
        # Save video metadata
        video_metadata = {
            "video_id": import_video_id,
            "title": f"YouTube: {video_data.get('title', video_id)}",
            "type": "youtube",
            "url": file_path,
            "status": "queued" if auto_process else "uploaded",
            "duration": 0,
            "userId": user_info['uid'],
            "filename": filename,
            "size": file_size,
            "created_at": datetime.now().isoformat(),
            "youtube_data": {
                "video_id": video_id,
                "title": video_data.get('title', ''),
                "channel": video_data.get('channel', {}),
                "metrics": video_data.get('metrics', {}),
                "url": f"https://www.youtube.com/watch?v={video_id}"
            }
        }
        
        # Load existing videos
        videos_file = os.path.join(uploads_dir, "videos.json")
        videos_list = []
        
        if os.path.exists(videos_file):
            with open(videos_file, "r") as f:
                videos_list = json.load(f)
        
        # Add new video
        videos_list.append(video_metadata)
        
        # Save updated list
        with open(videos_file, "w") as f:
            json.dump(videos_list, f, indent=2)
        
        # Trigger processing if auto_process is enabled
        if auto_process:
            try:
                task = process_video_local_task.delay(import_video_id, file_path)
                logger.info(f"Celery task triggered for YouTube video: {task.id}")
                video_metadata["status"] = "processing"
                
                # Update status in videos.json
                with open(videos_file, "w") as f:
                    json.dump(videos_list, f, indent=2)
            except Exception as celery_error:
                logger.error(f"Failed to trigger Celery task: {str(celery_error)}", exc_info=True)
                video_metadata["status"] = "queued"
        
        return {
            "success": True,
            "message": "Video imported successfully",
            "video_id": import_video_id,
            "status": video_metadata["status"],
            "youtube_data": video_metadata["youtube_data"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import YouTube video: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import video from YouTube: {str(e)}"
        )


@router.get("/categories")
async def get_video_categories(
    region: str = Query("US"),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get available video categories
    
    Args:
        region: Region code
        user_info: Authenticated user information
        
    Returns:
        List of video categories
    """
    try:
        categories = youtube_service.get_video_categories(region_code=region)
        
        return {
            "success": True,
            "count": len(categories),
            "categories": categories
        }
        
    except Exception as e:
        logger.error(f"Failed to get categories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get video categories"
        )
