"""Analysis retrieval API routes"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Dict, Any
import logging
import json
import csv
import io
from app.services.firebase_service import firebase_service
from app.api.dependencies import verify_auth_token
from app.models.schemas import AnalysisResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{video_id}", response_model=AnalysisResponse)
async def get_analysis(
    video_id: str,
    user_info: Dict[str, Any] = Depends(verify_auth_token)
):
    """
    Get full analysis results for a video
    
    Args:
        video_id: ID of the video
        user_info: Authenticated user information
        
    Returns:
        Complete analysis results
    """
    try:
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
