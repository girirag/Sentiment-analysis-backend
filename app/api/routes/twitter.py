"""Twitter API routes for fetching trending videos"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from typing import Dict, Any, List, Optional
import logging
import uuid
import os
from datetime import datetime
from app.services.twitter_service import twitter_service
from app.api.dependencies import verify_auth_token
from app.tasks.celery_tasks import process_video_local_task
import json

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search")
async def search_twitter_videos(
    query: str = Query("video", description="Search query"),
    max_results: int = Query(10, ge=1, le=100, description="Maximum results"),
    language: str = Query("en", description="Language code"),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Search Twitter for videos matching a query
    
    Args:
        query: Search query
        max_results: Maximum number of results (1-100)
        language: Language code
        user_info: Authenticated user information
        
    Returns:
        List of videos from Twitter
    """
    try:
        videos = twitter_service.search_trending_videos(
            query=query,
            max_results=max_results,
            language=language
        )
        
        return {
            "success": True,
            "count": len(videos),
            "videos": videos
        }
        
    except Exception as e:
        logger.error(f"Failed to search Twitter videos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search Twitter for videos"
        )


@router.get("/hashtag/{hashtag}")
async def search_by_hashtag(
    hashtag: str,
    max_results: int = Query(10, ge=1, le=100),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Search Twitter for videos by hashtag
    
    Args:
        hashtag: Hashtag to search (without #)
        max_results: Maximum number of results
        user_info: Authenticated user information
        
    Returns:
        List of videos with the hashtag
    """
    try:
        videos = twitter_service.search_by_hashtag(
            hashtag=hashtag,
            max_results=max_results
        )
        
        return {
            "success": True,
            "hashtag": hashtag,
            "count": len(videos),
            "videos": videos
        }
        
    except Exception as e:
        logger.error(f"Failed to search hashtag {hashtag}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search hashtag #{hashtag}"
        )


@router.get("/user/{username}")
async def search_by_user(
    username: str,
    max_results: int = Query(10, ge=1, le=100),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get videos from a specific Twitter user
    
    Args:
        username: Twitter username (without @)
        max_results: Maximum number of results
        user_info: Authenticated user information
        
    Returns:
        List of videos from the user
    """
    try:
        videos = twitter_service.search_by_user(
            username=username,
            max_results=max_results
        )
        
        return {
            "success": True,
            "username": username,
            "count": len(videos),
            "videos": videos
        }
        
    except Exception as e:
        logger.error(f"Failed to get videos from user {username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get videos from @{username}"
        )


@router.post("/import/{tweet_id}")
async def import_twitter_video(
    tweet_id: str,
    background_tasks: BackgroundTasks,
    auto_process: bool = Query(True, description="Automatically process video"),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Import a video from Twitter and optionally process it
    
    Args:
        tweet_id: Twitter tweet ID
        background_tasks: FastAPI background tasks
        auto_process: Whether to automatically process the video
        user_info: Authenticated user information
        
    Returns:
        Video import status
    """
    try:
        # Search for the specific tweet
        videos = twitter_service.search_trending_videos(
            query=f"tweet_id:{tweet_id}",
            max_results=1
        )
        
        if not videos:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tweet not found or does not contain video"
            )
        
        video_data = videos[0]
        video_url = video_data['video_url']
        
        # Generate unique video ID
        video_id = str(uuid.uuid4())
        
        # Get backend directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        uploads_dir = os.path.join(backend_dir, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Create filename
        filename = f"{video_id}_twitter_{tweet_id}.mp4"
        file_path = os.path.join(uploads_dir, filename)
        
        # Download video
        success = twitter_service.download_video(video_url, file_path)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to download video from Twitter"
            )
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Save video metadata
        video_metadata = {
            "video_id": video_id,
            "title": f"Twitter: {video_data['text'][:50]}...",
            "type": "twitter",
            "url": file_path,
            "status": "queued" if auto_process else "uploaded",
            "duration": video_data.get('duration_ms', 0) / 1000 if video_data.get('duration_ms') else 0,
            "userId": user_info['uid'],
            "filename": filename,
            "size": file_size,
            "created_at": datetime.now().isoformat(),
            "twitter_data": {
                "tweet_id": video_data['tweet_id'],
                "author": video_data['author'],
                "text": video_data['text'],
                "metrics": video_data['metrics'],
                "original_url": video_url
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
            background_tasks.add_task(
                process_video_local_task.delay,
                video_id,
                file_path
            )
            video_metadata["status"] = "processing"
        
        return {
            "success": True,
            "message": "Video imported successfully",
            "video_id": video_id,
            "status": video_metadata["status"],
            "twitter_data": video_metadata["twitter_data"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import Twitter video: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import video from Twitter"
        )


@router.post("/import-batch")
async def import_multiple_videos(
    tweet_ids: List[str],
    background_tasks: BackgroundTasks,
    auto_process: bool = Query(True),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Import multiple videos from Twitter
    
    Args:
        tweet_ids: List of tweet IDs
        background_tasks: FastAPI background tasks
        auto_process: Whether to automatically process videos
        user_info: Authenticated user information
        
    Returns:
        Batch import status
    """
    results = []
    
    for tweet_id in tweet_ids:
        try:
            result = await import_twitter_video(
                tweet_id=tweet_id,
                background_tasks=background_tasks,
                auto_process=auto_process,
                user_info=user_info
            )
            results.append({
                "tweet_id": tweet_id,
                "success": True,
                "video_id": result["video_id"]
            })
        except Exception as e:
            results.append({
                "tweet_id": tweet_id,
                "success": False,
                "error": str(e)
            })
    
    successful = sum(1 for r in results if r["success"])
    
    return {
        "success": True,
        "total": len(tweet_ids),
        "successful": successful,
        "failed": len(tweet_ids) - successful,
        "results": results
    }
