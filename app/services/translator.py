"""Translation service for multi-language support"""
import logging
from typing import Optional, List
from app.models.schemas import TranscriptionSegment

logger = logging.getLogger(__name__)


class Translator:
    """Service for translating text between languages"""
    
    def __init__(self):
        """Initialize translator with Google Translate"""
        try:
            from google.cloud import translate_v2
            self.client = translate_v2.Client()
            self.available = True
            logger.info("Google Translate client initialized successfully")
        except Exception as e:
            logger.warning(f"Google Translate not available: {str(e)}. Using fallback translation.")
            self.available = False
            self.client = None
    
    async def translate_text(self, text: str, source_language: str = "ta", target_language: str = "en") -> str:
        """
        Translate text from source to target language
        
        Args:
            text: Text to translate
            source_language: Source language code (default: "ta" for Tamil)
            target_language: Target language code (default: "en" for English)
            
        Returns:
            Translated text
        """
        if not text or not text.strip():
            return text
        
        try:
            if self.available and self.client:
                # Use Google Translate API
                result = self.client.translate_text(
                    text,
                    source_language=source_language,
                    target_language=target_language
                )
                translated = result['translatedText']
                logger.info(f"Translated {source_language} to {target_language}: {text[:50]}... -> {translated[:50]}...")
                return translated
            else:
                # Fallback: Use transformers library
                return await self._translate_with_transformers(text, source_language, target_language)
        except Exception as e:
            logger.error(f"Translation failed: {str(e)}")
            # Return original text if translation fails
            return text
    
    async def _translate_with_transformers(self, text: str, source_language: str, target_language: str) -> str:
        """
        Fallback translation using transformers library
        
        Args:
            text: Text to translate
            source_language: Source language code
            target_language: Target language code
            
        Returns:
            Translated text
        """
        try:
            from transformers import pipeline
            
            # Map language codes to model format
            lang_map = {
                "ta": "tam_Taml",  # Tamil
                "en": "eng_Latn",  # English
                "hi": "hin_Deva",  # Hindi
                "te": "tel_Telu",  # Telugu
                "ml": "mal_Mlym",  # Malayalam
                "kn": "kan_Knda",  # Kannada
            }
            
            src_lang = lang_map.get(source_language, source_language)
            tgt_lang = lang_map.get(target_language, target_language)
            
            # Use M2M100 model for translation
            translator = pipeline(
                "translation",
                model="facebook/m2m100_418M",
                src_lang=src_lang,
                tgt_lang=tgt_lang
            )
            
            result = translator(text, max_length=400)
            translated = result[0]['translation_text']
            
            logger.info(f"Translated (transformers) {source_language} to {target_language}")
            return translated
            
        except Exception as e:
            logger.error(f"Transformers translation failed: {str(e)}")
            return text
    
    async def translate_segments(
        self,
        segments: List[TranscriptionSegment],
        source_language: str = "ta",
        target_language: str = "en"
    ) -> List[TranscriptionSegment]:
        """
        Translate all segments
        
        Args:
            segments: List of transcription segments
            source_language: Source language code
            target_language: Target language code
            
        Returns:
            List of segments with translated text
        """
        translated_segments = []
        
        for segment in segments:
            translated_text = await self.translate_text(
                segment.text,
                source_language,
                target_language
            )
            
            # Create new segment with translated text
            translated_segment = TranscriptionSegment(
                text=translated_text,
                start=segment.start,
                end=segment.end,
                words=segment.words,
                original_text=segment.text,  # Keep original for reference
                original_language=source_language
            )
            translated_segments.append(translated_segment)
        
        return translated_segments
    
    def detect_language(self, text: str) -> str:
        """
        Detect the language of the text
        
        Args:
            text: Text to detect language for
            
        Returns:
            Language code (e.g., "ta" for Tamil, "en" for English)
        """
        try:
            if self.available and self.client:
                result = self.client.detect_language(text)
                language = result[0]['language']
                logger.info(f"Detected language: {language}")
                return language
            else:
                # Fallback language detection
                return self._detect_language_fallback(text)
        except Exception as e:
            logger.error(f"Language detection failed: {str(e)}")
            return "en"  # Default to English
    
    def _detect_language_fallback(self, text: str) -> str:
        """
        Fallback language detection using character ranges
        
        Args:
            text: Text to detect
            
        Returns:
            Language code
        """
        try:
            from langdetect import detect
            language = detect(text)
            return language
        except Exception as e:
            logger.warning(f"Fallback language detection failed: {str(e)}")
            return "en"


# Singleton instance
translator = Translator()
