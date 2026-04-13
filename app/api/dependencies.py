"""Shared API dependencies"""
from fastapi import Header, HTTPException, status
from typing import Optional, Dict, Any
from app.services.firebase_service import firebase_service
from app.config import settings
import os

async def verify_auth_token(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Verify Firebase authentication token and return user info
    
    Args:
        authorization: Authorization header with Bearer token
        
    Returns:
        User information dictionary
        
    Raises:
        HTTPException: If token is missing or invalid
    """
    # Development mode bypass
    if os.getenv("ENVIRONMENT") == "development" or settings.debug:
        if not authorization or authorization == "Bearer dev-token":
            return {
                "uid": "dev-user-123",
                "email": "dev@example.com",
                "name": "Development User"
            }
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    token = authorization.split("Bearer ")[1]
    
    try:
        user_info = await firebase_service.verify_token(token)
        return user_info
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify authentication token"
        )
