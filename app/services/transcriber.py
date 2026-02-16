"""Transcription service using OpenAI Whisper"""
import whisper
import logging
from typing import List, Optional
from app.models.schemas import TranscriptionSegment, Word
from app.config import settings
import numpy as np

logger = logging.getLogger(__name__)


class TranscriptionResult:
    """Container for transcription results"""
    
    def __init__(self, text: str, segments: List[TranscriptionSegment], language: str):
        self.text = text
        self.segments = segments
        self.language = language


class Transcriber:
    """Service for transcribing audio using Whisper"""
    
    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize Whisper transcriber
        
        Args:
            model_name: Whisper model size (tiny, base, small, medium, large)
        """
        self.model_name = model_name or settings.whisper_model
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load Whisper model"""
        try:
            logger.info(f"Loading Whisper model: {self.model_name}")
            self.model = whisper.load_model(self.model_name)
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {str(e)}")
            raise
    
    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> TranscriptionResult:
        """
        Transcribe audio file with word-level timestamps
        
        Args:
            audio_path: Path to the audio file
            language: Optional language code (auto-detected if not provided)
            
        Returns:
            TranscriptionResult with text, segments, and word-level timestamps
            
        Raises:
            RuntimeError: If transcription fails
        """
        try:
            logger.info(f"Transcribing audio: {audio_path}")
            
            # Transcribe with word-level timestamps
            result = self.model.transcribe(
                audio_path,
                language=language,
                word_timestamps=True,
                verbose=False
            )
            
            # Extract segments with word-level timestamps
            segments = []
            for segment in result['segments']:
                words = []
                
                # Extract word-level timestamps if available
                if 'words' in segment:
                    for word_data in segment['words']:
                        word = Word(
                            word=word_data['word'].strip(),
                            start=word_data['start'],
                            end=word_data['end']
                        )
                        words.append(word)
                
                transcription_segment = TranscriptionSegment(
                    text=segment['text'].strip(),
                    start=segment['start'],
                    end=segment['end'],
                    words=words
                )
                segments.append(transcription_segment)
            
            transcription_result = TranscriptionResult(
                text=result['text'],
                segments=segments,
                language=result['language']
            )
            
            logger.info(f"Transcription completed. Language: {result['language']}, Segments: {len(segments)}")
            return transcription_result
            
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise RuntimeError(f"Transcription failed: {str(e)}")
    
    async def transcribe_chunk(self, audio_bytes: bytes, language: Optional[str] = None) -> TranscriptionResult:
        """
        Transcribe an audio chunk (for live streams)
        
        Args:
            audio_bytes: Audio data as bytes
            language: Optional language code
            
        Returns:
            TranscriptionResult for the chunk
        """
        import tempfile
        import os
        
        try:
            # Save bytes to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name
            
            try:
                # Transcribe the temporary file
                result = await self.transcribe(temp_path, language)
                return result
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            logger.error(f"Chunk transcription failed: {str(e)}")
            raise RuntimeError(f"Chunk transcription failed: {str(e)}")
    
    async def transcribe_with_retry(self, audio_path: str, max_retries: int = 1) -> TranscriptionResult:
        """
        Transcribe audio with retry logic
        
        Args:
            audio_path: Path to the audio file
            max_retries: Maximum number of retries (default: 1)
            
        Returns:
            TranscriptionResult
            
        Raises:
            RuntimeError: If all retries fail
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt} for transcription")
                
                result = await self.transcribe(audio_path)
                return result
                
            except Exception as e:
                last_error = e
                logger.warning(f"Transcription attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries:
                    continue
                else:
                    logger.error(f"All transcription attempts failed")
                    raise RuntimeError(f"Transcription failed after {max_retries + 1} attempts: {str(last_error)}")
    
    def get_model_info(self) -> dict:
        """
        Get information about the loaded model
        
        Returns:
            Dictionary with model information
        """
        return {
            'model_name': self.model_name,
            'is_loaded': self.model is not None,
        }
