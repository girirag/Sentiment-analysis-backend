from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# Video Models
class VideoUploadResponse(BaseModel):
    video_id: str
    status: str
    message: str

class StreamStartRequest(BaseModel):
    stream_url: str
    title: str

class StreamStartResponse(BaseModel):
    video_id: str
    status: str
    websocket_url: str

# Transcription Models
class Word(BaseModel):
    word: str
    start: float
    end: float

class TranscriptionSegment(BaseModel):
    text: str
    start: float
    end: float
    sentiment: Optional[str] = None
    score: Optional[float] = None
    words: List[Word] = []
    original_text: Optional[str] = None  # Original text before translation
    original_language: Optional[str] = None  # Original language code (e.g., "ta" for Tamil)
    translated_text: Optional[str] = None  # Translated text
    translated_language: Optional[str] = None  # Target language code (e.g., "en" for English)

# Sentiment Models
class SentimentResult(BaseModel):
    sentiment: str  # "positive", "negative", "neutral"
    score: float  # -1 to 1
    confidence: float  # 0 to 1
    timestamp: float

# Keyword Models
class KeywordContext(BaseModel):
    timestamp: float
    text: str

class KeywordData(BaseModel):
    word: str
    count: int
    timestamps: List[float]
    avg_sentiment: float = 0.0
    contexts: List[KeywordContext] = []

# Timeline Models
class TimelinePoint(BaseModel):
    timestamp: float
    sentiment: str
    score: float

# Analysis Models
class AnalysisSummary(BaseModel):
    overall_sentiment: str
    avg_score: float
    total_keywords: int
    duration: float
    positive_percentage: float
    negative_percentage: float
    neutral_percentage: float

class AnalysisResponse(BaseModel):
    video_id: str
    status: str
    transcription: List[TranscriptionSegment]
    keywords: List[KeywordData]
    timeline: List[TimelinePoint]
    summary: AnalysisSummary

# Error Models
class ErrorResponse(BaseModel):
    error: str
    detail: str
    timestamp: str
    path: Optional[str] = None
    request_id: Optional[str] = None

# Clip Highlights Models

class ClipGenerateResponse(BaseModel):
    job_id: str
    status: str  # "queued"

class ClipJobStatus(BaseModel):
    job_id: str
    video_id: str
    status: str
    clip_ids: list[str] = []
    error: Optional[str] = None

class ClipResult(BaseModel):
    clip_id: str
    video_id: str
    start_time: float
    end_time: float
    matched_text: str
    dataset_entry: str
    similarity_score: float
    storage_path: str

class ClipDownloadResponse(BaseModel):
    clip_id: str
    download_url: str
    expires_in: int  # seconds
