FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip setuptools wheel packaging

# Install CPU-only torch first
RUN pip install --no-cache-dir \
    "torch==2.2.0+cpu" \
    "torchaudio==2.2.0+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwor
RUN pip install --no-cache-dir -r requirements-prod.txt

# Download NLTK data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

# Copy application code
COPY . .

RUN mkdir -p uploads
RUN chmod +x start.sh

EXPOSE 8000

# Runs FastAPI + Celery worker together in one container
CMD ["bash", "start.sh"]
