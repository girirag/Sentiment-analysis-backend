FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip setuptools wheel packaging

# Install CPU-only torch first (avoids CUDA bloat)
RUN pip install --no-cache-dir \
    "torch==2.2.0+cpu" \
    "torchaudio==2.2.0+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy app code
COPY . .

# Download NLTK data using a script (avoids shell quoting issues)
RUN python download_nltk.py

RUN mkdir -p uploads
RUN chmod +x start.sh

EXPOSE 8000

CMD ["bash", "start.sh"]
