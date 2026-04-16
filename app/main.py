from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.services.firebase_service import firebase_service
from app.api.routes import video, analysis, websocket, twitter, youtube
from app.api.routes.clips import router as clips_router
from app.utils.error_handlers import register_error_handlers
import logging
import os
import glob

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

# CRITICAL: Configure CORS BEFORE including routers
FRONTEND_URL = os.getenv("FRONTEND_URL", "")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Production Vercel frontend
    "https://sentiment-analysis-frontend-ivory.vercel.app",
]

# Add any additional frontend URL from env var
if FRONTEND_URL and FRONTEND_URL not in origins:
    origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Get the backend directory (parent of app directory)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Serve analysis JSON files statically
uploads_path = os.path.join(BACKEND_DIR, "uploads")
if os.path.exists(uploads_path):
    app.mount("/static/analysis", StaticFiles(directory=uploads_path), name="analysis")
else:
    logger.warning(f"Uploads directory not found at: {uploads_path}")

# Serve video files
@app.options("/api/videos/stream/{video_id}")
async def stream_video_options(video_id: str):
    """Handle OPTIONS request for video streaming"""
    return {"message": "OK"}

@app.get("/api/videos/stream/{video_id}")
@app.head("/api/videos/stream/{video_id}")
async def stream_video(video_id: str):
    """Stream video file for playback"""
    # Find video file
    video_pattern = os.path.join(uploads_path, f"{video_id}_*")
    video_files = glob.glob(video_pattern)
    
    # Filter for video extensions
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv']
    video_files = [f for f in video_files if any(f.lower().endswith(ext) for ext in video_extensions)]
    
    if video_files:
        video_path = video_files[0]
        return FileResponse(
            video_path,
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Disposition": f"inline; filename={os.path.basename(video_path)}"
            }
        )
    
    raise HTTPException(status_code=404, detail="Video file not found")

# Add OPTIONS handler for preflight requests
@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    return {"message": "OK"}

@app.get("/")
async def root():
    return {"message": "Video Sentiment Analysis API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Serve the standalone viewer
@app.get("/viewer")
async def serve_viewer():
    viewer_path = os.path.join(BACKEND_DIR, "view_analysis.html")
    
    if os.path.exists(viewer_path):
        return FileResponse(viewer_path, media_type="text/html")
    
    return {"error": "Viewer not found", "backend_dir": BACKEND_DIR, "tried": viewer_path}

# Include routers AFTER CORS middleware
app.include_router(video.router, prefix="/api/videos", tags=["videos"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(websocket.router, tags=["websocket"])
app.include_router(twitter.router, prefix="/api/twitter", tags=["twitter"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])
app.include_router(clips_router, prefix="/api/videos/{video_id}/clips", tags=["clips"])

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

