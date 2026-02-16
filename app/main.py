from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.services.firebase_service import firebase_service
from app.api.routes import video, analysis, websocket
from app.utils.error_handlers import register_error_handlers
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video Sentiment Analysis API",
    version="1.0.0",
    description="API for analyzing sentiment in videos with keyword tracking"
)

# Register error handlers
register_error_handlers(app)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(video.router, prefix="/api/videos", tags=["videos"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(websocket.router, tags=["websocket"])

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting Video Sentiment Analysis API...")
    try:
        # Initialize Firebase (singleton pattern ensures it's only initialized once)
        _ = firebase_service
        logger.info("Firebase service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase service: {str(e)}")
        # Continue startup even if Firebase fails (for development)

@app.get("/")
async def root():
    return {"message": "Video Sentiment Analysis API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
