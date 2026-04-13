from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # Firebase
    firebase_credentials_path: str = Field(default="./firebase-key.json")
    firebase_storage_bucket: str = Field(default="")
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379")
    
    # Whisper
    whisper_model: str = Field(default="base")
    
    # Sentiment Analysis
    sentiment_model: str = Field(default="distilbert-base-uncased-finetuned-sst-2-english")
    
    # Video Processing
    max_video_size_mb: int = Field(default=500, alias="MAX_VIDEO_SIZE")
    stream_chunk_duration: int = Field(default=10)
    
    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    
    # Environment
    environment: str = Field(default="production")
    debug: bool = Field(default=False)
    
    # Twitter API (optional)
    twitter_api_key: str = Field(default="")
    twitter_api_secret: str = Field(default="")
    twitter_bearer_token: str = Field(default="")
    twitter_access_token: str = Field(default="")
    twitter_access_token_secret: str = Field(default="")
    
    # YouTube API (optional)
    youtube_api_key: str = Field(default="")
    
    # Google Translate API (optional)
    google_translate_api_key: str = Field(default="")
    google_cloud_project_id: str = Field(default="sentiment-analysis-tamil")
    
    class Config:
        env_file = ".env"
        populate_by_name = True

settings = Settings()
