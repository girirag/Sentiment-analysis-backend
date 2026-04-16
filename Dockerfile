FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip + setuptools first (pkg_resources comes from setuptools)
RUN pip install --upgrade pip setuptools wheel packaging

# Install CPU-only torch (must be before other ML packages)
RUN pip install --no-cache-dir \
    "torch==2.2.0+cpu" \
    "torchaudio==2.2.0+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining prod dependencies
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Download NLTK data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

# Copy application code
COPY . .

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
