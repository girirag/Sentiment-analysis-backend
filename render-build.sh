#!/usr/bin/env bash
# Render build script for Video Sentiment Analysis Backend
set -o errexit

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing CPU-only torch first (avoids CUDA bloat)..."
pip install --no-cache-dir torch==2.2.0+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

echo "==> Installing remaining production dependencies..."
pip install --no-cache-dir -r requirements-prod.txt

echo "==> Downloading NLTK data..."
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

echo "==> Build complete!"
