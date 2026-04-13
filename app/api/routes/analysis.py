"""Analysis retrieval API routes"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Dict, Any
import logging
import json
import csv
import io
import os
from app.services.firebase_service import firebase_service
from app.api.dependencies import verify_auth_token
from app.models.schemas import AnalysisResponse
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# CORS headers for responses
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "http://localhost:5173",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


@router.get("/{video_id}", response_model=AnalysisResponse)
async def get_analysis(
    video_id: str,
    response: Response,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get full analysis results for a video
    
    Args:
        video_id: ID of the video
        response: Response object to add headers
        user_info: Authenticated user information
        
    Returns:
        Complete analysis results
    """
    # Add CORS headers
    for key, value in CORS_HEADERS.items():
        response.headers[key] = value
    
    try:
        # Development mode: Read from local analysis files
        if settings.environment == "development":
            # Get the backend directory (parent of app directory)
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            uploads_dir = os.path.join(backend_dir, "uploads")
            videos_file = os.path.join(uploads_dir, "videos.json")
            analysis_file = os.path.join(uploads_dir, f"{video_id}_analysis.json")
            
            logger.info(f"Looking for video {video_id}")
            logger.info(f"Backend dir: {backend_dir}")
            logger.info(f"Uploads dir: {uploads_dir}")
            logger.info(f"Videos file: {videos_file}")
            logger.info(f"Videos file exists: {os.path.exists(videos_file)}")
            
            # Check if video exists
            if os.path.exists(videos_file):
                with open(videos_file, "r") as f:
                    videos = json.load(f)
                
                logger.info(f"Loaded {len(videos)} videos from file")
                logger.info(f"User ID from auth: {user_info['uid']}")
                
                video = next((v for v in videos if v['video_id'] == video_id), None)
                
                if not video:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Video not found"
                    )
                
                if video['userId'] != user_info['uid']:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to access this video"
                    )
                
                # Check if analysis file exists
                if os.path.exists(analysis_file):
                    with open(analysis_file, "r", encoding='utf-8') as f:
                        analysis_data = json.load(f)
                    
                    # Return actual analysis data
                    return {
                        "video_id": video_id,
                        "overall_sentiment": analysis_data.get('overall_sentiment', 'neutral'),
                        "sentiment_scores": {
                            "positive": analysis_data['sentiment_breakdown']['positive'] / analysis_data['sentiment_breakdown']['total'],
                            "negative": analysis_data['sentiment_breakdown']['negative'] / analysis_data['sentiment_breakdown']['total'],
                            "neutral": 0.0
                        },
                        "timeline": analysis_data.get('timeline', []),
                        "keywords": analysis_data.get('keywords', []),
                        "transcription": analysis_data.get('transcription', ''),
                        "status": "completed"
                    }
                else:
                    # Return mock data if no analysis yet
                    return {
                        "video_id": video_id,
                        "overall_sentiment": "pending",
                        "sentiment_scores": {
                            "positive": 0.0,
                            "neutral": 0.0,
                            "negative": 0.0
                        },
                        "timeline": [],
                        "keywords": [],
                        "transcription": "Analysis pending...",
                        "status": "queued"
                    }
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Video not found"
                )
        
        # Production mode: Get from Firebase
        # Verify video ownership
        video = await firebase_service.get_video(video_id)
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        if video['userId'] != user_info['uid']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this video"
            )
        
        # Get analysis
        analysis = await firebase_service.get_analysis(video_id)
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found for this video"
            )
        
        return analysis
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analysis"
        )


@router.get("/{video_id}/timeline")
async def get_timeline(
    video_id: str,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get sentiment timeline for a video
    
    Args:
        video_id: ID of the video
        user_info: Authenticated user information
        
    Returns:
        Sentiment timeline data
    """
    try:
        # Verify ownership
        video = await firebase_service.get_video(video_id)
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        if video['userId'] != user_info['uid']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized"
            )
        
        # Get analysis
        analysis = await firebase_service.get_analysis(video_id)
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        return {"timeline": analysis.get('timeline', [])}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get timeline: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve timeline"
        )


@router.get("/{video_id}/keywords")
async def get_keywords(
    video_id: str,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get keyword data for a video
    
    Args:
        video_id: ID of the video
        user_info: Authenticated user information
        
    Returns:
        Keyword tracking data
    """
    try:
        # Verify ownership
        video = await firebase_service.get_video(video_id)
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        if video['userId'] != user_info['uid']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized"
            )
        
        # Get analysis
        analysis = await firebase_service.get_analysis(video_id)
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        return {"keywords": analysis.get('keywords', [])}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get keywords: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve keywords"
        )


@router.get("/{video_id}/export")
async def export_analysis(
    video_id: str,
    format: str = Query("json", regex="^(json|csv)$"),
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Export analysis results in JSON or CSV format
    
    Args:
        video_id: ID of the video
        format: Export format (json or csv)
        user_info: Authenticated user information
        
    Returns:
        Downloadable file
    """
    try:
        # Verify ownership
        video = await firebase_service.get_video(video_id)
        
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )
        
        if video['userId'] != user_info['uid']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized"
            )
        
        # Get analysis
        analysis = await firebase_service.get_analysis(video_id)
        
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found"
            )
        
        if format == "json":
            # Export as JSON
            json_data = json.dumps(analysis, indent=2)
            
            return StreamingResponse(
                io.BytesIO(json_data.encode()),
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=analysis_{video_id}.json"
                }
            )
        
        elif format == "csv":
            # Export timeline as CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(["timestamp", "sentiment", "score"])
            
            # Write timeline data
            for point in analysis.get('timeline', []):
                writer.writerow([
                    point.get('timestamp', 0),
                    point.get('sentiment', 'neutral'),
                    point.get('score', 0.0)
                ])
            
            csv_data = output.getvalue()
            
            return StreamingResponse(
                io.BytesIO(csv_data.encode()),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=timeline_{video_id}.csv"
                }
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export analysis"
        )
