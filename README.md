# Video Sentiment Analysis - Backend API

AI-powered video sentiment analysis backend built with FastAPI, Whisper, and DistilBERT.

## 🚀 Features

- **Video Upload & Processing** - Support for MP4, AVI, MOV, MKV formats
- **Live Stream Analysis** - Real-time processing of RTMP/HTTP/HTTPS streams
- **Speech-to-Text** - OpenAI Whisper with word-level timestamps
- **Sentiment Analysis** - DistilBERT transformer model
- **Keyword Tracking** - TF-IDF extraction + custom keywords
- **Real-time Updates** - WebSocket support for live progress
- **Background Processing** - Celery + Redis for async tasks
- **Cloud Storage** - Firebase Firestore + Storage
- **Export** - JSON and CSV formats

## 📋 Prerequisites

- Python 3.11+
- Redis
- FFmpeg
- Firebase project with credentials

## 🛠️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/video-sentiment-backend.git
cd video-sentiment-backend
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use winget:
```bash
winget install --id=Gyan.FFmpeg -e
```

### 5. Set up Firebase

1. Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com)
2. Enable Firestore and Storage
3. Download service account key as `firebase-key.json`
4. Place it in the backend root directory

### 6. Configure environment variables

Create `.env` file:

```env
# Firebase
FIREBASE_CREDENTIALS_PATH=./firebase-key.json
FIREBASE_STORAGE_BUCKET=your-project.appspot.com

# Redis
REDIS_URL=redis://localhost:6379

# Models
WHISPER_MODEL=base
SENTIMENT_MODEL=distilbert-base-uncased-finetuned-sst-2-english

# Processing
MAX_VIDEO_SIZE=500
STREAM_CHUNK_DURATION=10

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### 7. Start Redis

```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or install locally
redis-server
```

## 🚀 Running the Application

### Development Mode

**Terminal 1 - API Server:**
```bash
uvicorn app.main:app --reload
```

**Terminal 2 - Celery Worker:**
```bash
# Linux/Mac
celery -A app.tasks.celery_tasks worker --loglevel=info

# Windows
celery -A app.tasks.celery_tasks worker --loglevel=info --pool=solo
```

### Using Docker Compose

```bash
docker-compose up -d
```

## 📡 API Endpoints

### Video Management
- `POST /api/videos/upload` - Upload video file
- `POST /api/videos/stream/start` - Start live stream
- `POST /api/videos/stream/stop/{video_id}` - Stop stream
- `GET /api/videos/{video_id}` - Get video details
- `GET /api/videos/` - List all videos

### Analysis
- `GET /api/analysis/{video_id}` - Get full analysis
- `GET /api/analysis/{video_id}/timeline` - Get sentiment timeline
- `GET /api/analysis/{video_id}/keywords` - Get keywords
- `GET /api/analysis/{video_id}/export` - Export results (JSON/CSV)

### WebSocket
- `WS /ws/analysis/{video_id}` - Real-time updates

### System
- `GET /` - API information
- `GET /health` - Health check

## 📚 API Documentation

Interactive API documentation available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## 🧪 Testing

### Run all tests
```bash
pytest
```

### Run specific test suite
```bash
pytest tests/test_services.py -v
pytest tests/test_api_endpoints.py -v
pytest tests/test_properties.py -v
```

### Run with coverage
```bash
pytest --cov=app --cov-report=html
```

## 🏗️ Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration
│   ├── api/
│   │   └── routes/             # API endpoints
│   ├── services/               # Core services
│   ├── models/                 # Pydantic models
│   ├── tasks/                  # Celery tasks
│   └── utils/                  # Utilities
├── tests/                      # Test suite
├── requirements.txt            # Dependencies
├── Dockerfile                  # Docker configuration
└── .env.example               # Environment template
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREBASE_CREDENTIALS_PATH` | Path to Firebase key | `./firebase-key.json` |
| `FIREBASE_STORAGE_BUCKET` | Firebase storage bucket | - |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `WHISPER_MODEL` | Whisper model size | `base` |
| `SENTIMENT_MODEL` | HuggingFace model | `distilbert-base-uncased-finetuned-sst-2-english` |
| `MAX_VIDEO_SIZE` | Max video size (MB) | `500` |
| `STREAM_CHUNK_DURATION` | Stream chunk duration (s) | `10` |

### Whisper Models

Available models (size vs accuracy tradeoff):
- `tiny` - Fastest, lowest accuracy
- `base` - Good balance (recommended)
- `small` - Better accuracy
- `medium` - High accuracy
- `large` - Best accuracy, slowest

## 🐳 Docker Deployment

### Build image
```bash
docker build -t video-sentiment-backend .
```

### Run container
```bash
docker run -d \
  -p 8000:8000 \
  -e REDIS_URL=redis://host.docker.internal:6379 \
  -v $(pwd)/firebase-key.json:/app/firebase-key.json:ro \
  video-sentiment-backend
```

## 📊 Performance

- **Processing Time:** ~2-3 minutes per minute of video
- **API Response:** <2 seconds
- **WebSocket Updates:** Every 2 seconds
- **Export Generation:** <5 seconds

## 🔒 Security

- Token-based authentication
- Request validation with Pydantic
- File type and size validation
- Firebase security rules
- Environment variable configuration

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [OpenAI Whisper](https://github.com/openai/whisper) - Speech recognition
- [HuggingFace Transformers](https://huggingface.co/transformers/) - Sentiment analysis
- [Firebase](https://firebase.google.com/) - Cloud services
- [Celery](https://docs.celeryproject.org/) - Distributed task queue

## 📧 Support

For issues and questions:
- Open an issue on GitHub
- Check the [API documentation](http://localhost:8000/docs)
- Review the test suite for examples

## 🔗 Related

- [Frontend Repository](https://github.com/yourusername/video-sentiment-frontend)
- [Full Documentation](https://github.com/yourusername/video-sentiment-docs)
