FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Use /code as workdir to avoid confusion with the 'app' package name
WORKDIR /code

ENV PYTHONPATH=/code

RUN pip install --upgrade pip setuptools wheel packaging

# Install CPU-only torch first
RUN pip install --no-cache-dir \
    "torch==2.2.0+cpu" \
    "torchaudio==2.2.0+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Copy and install dependencies
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy all app code
COPY . .

# Download NLTK data
RUN python download_nltk.py

RUN mkdir -p uploads
RUN chmod +x start.sh

EXPOSE 8000

CMD ["bash", "start.sh"]
