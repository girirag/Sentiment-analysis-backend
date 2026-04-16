"""Transcription service — uses faster-whisper in production, openai-whisper locally"""
import logging
from typing import List, Optional
from app.models.schemas import TranscriptionSegment, Word
from app.config import settings

logger = logging.getLogger(__name__)


class TranscriptionResult:
    def __init__(self, text: str, segments: List[TranscriptionSegment], language: str):
        self.text = text
        self.segments = segments
        self.language = language


class Transcriber:
    """Transcription service — auto-selects faster-whisper or openai-whisper"""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.whisper_model
        self.model = None
        self._use_faster = False
        self._load_model()

    def _load_model(self):
        # Try faster-whisper first (production), fall back to openai-whisper (local dev)
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading faster-whisper model: {self.model_name}")
            self.model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8"
            )
            self._use_faster = True
            logger.info("faster-whisper model loaded successfully")
        except ImportError:
            try:
                import whisper
                logger.info(f"Loading openai-whisper model: {self.model_name}")
                self.model = whisper.load_model(self.model_name)
                self._use_faster = False
                logger.info("openai-whisper model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load any Whisper model: {str(e)}")
                raise

    async def transcribe(self, audio_path: str, language: Optional[str] = None) -> TranscriptionResult:
        try:
            logger.info(f"Transcribing audio: {audio_path}")

            if self._use_faster:
                return await self._transcribe_faster(audio_path, language)
            else:
                return await self._transcribe_openai(audio_path, language)

        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise RuntimeError(f"Transcription failed: {str(e)}")

    async def _transcribe_faster(self, audio_path: str, language: Optional[str]) -> TranscriptionResult:
        """faster-whisper transcription"""
        fw_segments, info = self.model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True
        )

        segments = []
        full_text_parts = []

        for seg in fw_segments:
            words = []
            if seg.words:
                for w in seg.words:
                    words.append(Word(word=w.word.strip(), start=w.start, end=w.end))

            segments.append(TranscriptionSegment(
                text=seg.text.strip(),
                start=seg.start,
                end=seg.end,
                words=words
            ))
            full_text_parts.append(seg.text.strip())

        full_text = " ".join(full_text_parts)
        detected_language = info.language if hasattr(info, 'language') else (language or "en")

        logger.info(f"Transcription done. Language: {detected_language}, Segments: {len(segments)}")
        return TranscriptionResult(text=full_text, segments=segments, language=detected_language)

    async def _transcribe_openai(self, audio_path: str, language: Optional[str]) -> TranscriptionResult:
        """openai-whisper transcription"""
        result = self.model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            verbose=False
        )

        segments = []
        for segment in result['segments']:
            words = []
            if 'words' in segment:
                for word_data in segment['words']:
                    words.append(Word(
                        word=word_data['word'].strip(),
                        start=word_data['start'],
                        end=word_data['end']
                    ))
            segments.append(TranscriptionSegment(
                text=segment['text'].strip(),
                start=segment['start'],
                end=segment['end'],
                words=words
            ))

        logger.info(f"Transcription done. Language: {result['language']}, Segments: {len(segments)}")
        return TranscriptionResult(text=result['text'], segments=segments, language=result['language'])

    async def transcribe_chunk(self, audio_bytes: bytes, language: Optional[str] = None) -> TranscriptionResult:
        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as f:
            f.write(audio_bytes)
            tmp = f.name
        try:
            return await self.transcribe(tmp, language)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    async def transcribe_with_retry(self, audio_path: str, max_retries: int = 1) -> TranscriptionResult:
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt}")
                return await self.transcribe(audio_path)
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
        raise RuntimeError(f"Transcription failed after {max_retries + 1} attempts: {str(last_error)}")

    def get_model_info(self) -> dict:
        return {'model_name': self.model_name, 'is_loaded': self.model is not None,
                'backend': 'faster-whisper' if self._use_faster else 'openai-whisper'}
