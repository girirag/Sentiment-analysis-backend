#!/usr/bin/env bash
# Render build script for Video Sentiment Analysis Backend

set -o errexit

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Downloading NLTK data..."
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

echo "Build completed successfully!"
