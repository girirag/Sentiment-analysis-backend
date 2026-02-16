from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base exception for application errors"""
    def __init__(self, message: str, status_code: int = 500, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class VideoProcessingError(AppException):
    """Exception for video processing errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)


class TranscriptionError(AppException):
    """Exception for transcription errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, details)


class SentimentAnalysisError(AppException):
    """Exception for sentiment analysis errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, details)


class FirebaseError(AppException):
    """Exception for Firebase errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, status.HTTP_503_SERVICE_UNAVAILABLE, details)


class AuthenticationError(AppException):
    """Exception for authentication errors"""
    def __init__(self, message: str = "Authentication failed", details: dict = None):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED, details)


class AuthorizationError(AppException):
    """Exception for authorization errors"""
    def __init__(self, message: str = "Access denied", details: dict = None):
        super().__init__(message, status.HTTP_403_FORBIDDEN, details)


class ResourceNotFoundError(AppException):
    """Exception for resource not found errors"""
    def __init__(self, resource: str, resource_id: str):
        message = f"{resource} with ID '{resource_id}' not found"
        super().__init__(message, status.HTTP_404_NOT_FOUND, {"resource": resource, "id": resource_id})


async def app_exception_handler(request: Request, exc: AppException):
    """Handler for custom application exceptions"""
    logger.error(f"Application error: {exc.message}", extra={
        "status_code": exc.status_code,
        "details": exc.details,
        "path": request.url.path
    })
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "details": exc.details,
            "path": str(request.url.path)
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handler for request validation errors"""
    logger.warning(f"Validation error: {exc.errors()}", extra={"path": request.url.path})
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "details": exc.errors(),
            "path": str(request.url.path)
        }
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handler for HTTP exceptions"""
    logger.warning(f"HTTP error {exc.status_code}: {exc.detail}", extra={"path": request.url.path})
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "path": str(request.url.path)
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handler for unhandled exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True, extra={"path": request.url.path})
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
            "path": str(request.url.path)
        }
    )


def register_error_handlers(app):
    """Register all error handlers with the FastAPI app"""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
