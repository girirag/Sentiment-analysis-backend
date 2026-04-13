"""Live stream processing service"""
import os
import subprocess
import threading
import time
import logging
from typing import Optional, Callable
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)


class StreamProcessor:
    """Process live video streams in real-time"""
    
    def __init__(self, stream_url: str, video_id: str, chunk_duration: int = 10):
        """
        Initialize stream processor
        
        Args:
            stream_url: URL of the live stream
            video_id: Unique identifier for this stream
            chunk_duration: Duration of each chunk in seconds
        """
        self.stream_url = stream_url
        self.video_id = video_id
        self.chunk_duration = chunk_duration
        self.is_running = False
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.chunk_callback: Optional[Callable] = None
        
        # Create directories
        self.output_dir = Path(f"stream_chunks/{video_id}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.chunk_index = 0
    
    def start(self, chunk_callback: Optional[Callable] = None):
        """
        Start capturing and processing the stream
        
        Args:
            chunk_callback: Function to call when a chunk is ready
        """
        if self.is_running:
            logger.warning(f"Stream {self.video_id} is already running")
            return
        
        self.chunk_callback = chunk_callback
        self.is_running = True
        
        # Start capture thread
        self.thread = threading.Thread(target=self._capture_stream, daemon=True)
        self.thread.start()
        
        logger.info(f"Started stream processing for {self.video_id}")
    
    def stop(self):
        """Stop capturing the stream"""
        self.is_running = False
        
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                logger.error(f"Error stopping stream process: {str(e)}")
        
        if self.thread:
            self.thread.join(timeout=10)
        
        logger.info(f"Stopped stream processing for {self.video_id}")
    
    def _capture_stream(self):
        """Capture stream and split into chunks"""
        try:
            # Use ffmpeg to capture stream in chunks
            chunk_pattern = str(self.output_dir / f"chunk_%03d.mp4")
            
            cmd = [
                'ffmpeg',
                '-i', self.stream_url,
                '-f', 'segment',
                '-segment_time', str(self.chunk_duration),
                '-segment_format', 'mp4',
                '-reset_timestamps', '1',
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-ar', '16000',
                '-ac', '1',
                chunk_pattern,
                '-y'
            ]
            
            logger.info(f"Starting ffmpeg capture: {' '.join(cmd)}")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Monitor for new chunks
            self._monitor_chunks()
            
        except Exception as e:
            logger.error(f"Error capturing stream: {str(e)}", exc_info=True)
            self.is_running = False
    
    def _monitor_chunks(self):
        """Monitor directory for new chunks and process them"""
        processed_chunks = set()
        
        while self.is_running:
            try:
                # Check for new chunk files
                chunk_files = sorted(self.output_dir.glob("chunk_*.mp4"))
                
                for chunk_file in chunk_files:
                    if chunk_file not in processed_chunks:
                        # Wait a moment to ensure file is fully written
                        time.sleep(1)
                        
                        if chunk_file.stat().st_size > 0:
                            logger.info(f"New chunk detected: {chunk_file.name}")
                            processed_chunks.add(chunk_file)
                            
                            if self.chunk_callback:
                                try:
                                    self.chunk_callback(str(chunk_file), self.chunk_index)
                                except Exception as e:
                                    logger.error(f"Error in chunk callback: {str(e)}")
                            
                            self.chunk_index += 1
                
                time.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring chunks: {str(e)}")
                time.sleep(5)
    
    def get_chunk_count(self) -> int:
        """Get the number of chunks processed"""
        return self.chunk_index
    
    def cleanup(self):
        """Clean up chunk files"""
        try:
            import shutil
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir)
                logger.info(f"Cleaned up chunks for {self.video_id}")
        except Exception as e:
            logger.error(f"Error cleaning up chunks: {str(e)}")


class StreamChunkProcessor:
    """Process individual stream chunks"""
    
    def __init__(self):
        """Initialize chunk processor"""
        from app.services.transcriber import Transcriber
        from app.services.sentiment_analyzer import SentimentAnalyzer
        from app.services.keyword_tracker import KeywordTracker
        
        self.transcriber = Transcriber()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.keyword_tracker = KeywordTracker()
    
    async def process_chunk(self, chunk_path: str, chunk_index: int):
        """
        Process a single stream chunk
        
        Args:
            chunk_path: Path to the chunk file
            chunk_index: Index of this chunk
            
        Returns:
            Dictionary with analysis results
        """
        try:
            logger.info(f"Processing chunk {chunk_index}: {chunk_path}")
            
            # Extract audio from chunk
            audio_path = chunk_path.replace('.mp4', '.wav')
            await self._extract_audio(chunk_path, audio_path)
            
            # Transcribe
            transcription = await self.transcriber.transcribe_with_retry(audio_path)
            
            # Analyze sentiment
            timeline = await self.sentiment_analyzer._create_timeline_async(transcription.segments)
            
            # Extract keywords
            keywords = await self.keyword_tracker.extract_keywords(
                transcription.text,
                segments=transcription.segments
            )
            
            # Calculate sentiment for keywords
            keywords = await self.keyword_tracker.calculate_keyword_sentiment(
                keywords,
                transcription.segments
            )
            
            # Calculate summary
            summary_stats = self.sentiment_analyzer.calculate_summary(timeline)
            
            # Clean up audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            result = {
                'chunk_index': chunk_index,
                'transcription': [seg.dict() for seg in transcription.segments],
                'keywords': [kw.dict() for kw in keywords],
                'timeline': [point.dict() for point in timeline],
                'summary': summary_stats
            }
            
            logger.info(f"Chunk {chunk_index} processed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_index}: {str(e)}", exc_info=True)
            raise
    
    async def _extract_audio(self, video_path: str, audio_path: str):
        """Extract audio from video chunk"""
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            audio_path,
            '-y'
        ]
        
        process = subprocess.run(cmd, capture_output=True)
        
        if process.returncode != 0:
            raise RuntimeError(f"Failed to extract audio: {process.stderr.decode()}")
