"""Live stream handling service"""
import asyncio
import logging
import ffmpeg
from typing import Optional, Dict
from app.config import settings
import tempfile
import os

logger = logging.getLogger(__name__)


class StreamHandler:
    """Service for handling live video streams"""
    
    def __init__(self):
        """Initialize stream handler"""
        self.active_streams: Dict[str, asyncio.Task] = {}
        self.chunk_duration = settings.stream_chunk_duration
    
    def _validate_stream_url(self, stream_url: str) -> bool:
        """
        Validate if stream URL is supported
        
        Args:
            stream_url: Stream URL to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check for RTMP or HTTP/HTTPS (for HLS/DASH)
        supported_protocols = ['rtmp://', 'rtmps://', 'http://', 'https://']
        return any(stream_url.startswith(protocol) for protocol in supported_protocols)
    
    async def start_stream(self, stream_url: str, video_id: str) -> None:
        """
        Start capturing and processing a live stream
        
        Args:
            stream_url: URL of the live stream
            video_id: ID of the video document
            
        Raises:
            ValueError: If stream URL is invalid
            RuntimeError: If stream connection fails
        """
        try:
            # Validate stream URL
            if not self._validate_stream_url(stream_url):
                raise ValueError("Unsupported stream protocol. Supported: RTMP, RTMPS, HTTP, HTTPS")
            
            logger.info(f"Starting stream capture for video_id: {video_id}")
            
            # Test stream connection with timeout
            try:
                probe = await asyncio.wait_for(
                    asyncio.to_thread(ffmpeg.probe, stream_url),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                raise RuntimeError("Stream connection timeout (10 seconds)")
            except ffmpeg.Error as e:
                raise RuntimeError(f"Failed to connect to stream: {str(e)}")
            
            # Create async task for stream processing
            task = asyncio.create_task(self._process_stream(stream_url, video_id))
            self.active_streams[video_id] = task
            
            logger.info(f"Stream started successfully for video_id: {video_id}")
            
        except ValueError:
            raise
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed to start stream: {str(e)}")
            raise RuntimeError(f"Failed to start stream: {str(e)}")
    
    async def _process_stream(self, stream_url: str, video_id: str) -> None:
        """
        Process stream in chunks
        
        Args:
            stream_url: URL of the stream
            video_id: ID of the video
        """
        try:
            chunk_index = 0
            
            while video_id in self.active_streams:
                # Capture chunk
                audio_chunk = await self.capture_chunk(stream_url, self.chunk_duration)
                
                if audio_chunk:
                    # Process chunk asynchronously
                    from app.tasks.celery_tasks import process_stream_chunk
                    process_stream_chunk.delay(video_id, audio_chunk, chunk_index)
                    
                    chunk_index += 1
                else:
                    # Stream ended
                    break
                
                # Small delay between chunks
                await asyncio.sleep(0.1)
            
            logger.info(f"Stream processing completed for video_id: {video_id}")
            
        except Exception as e:
            logger.error(f"Stream processing error: {str(e)}")
    
    async def capture_chunk(self, stream_url: str, duration: int = 10) -> Optional[bytes]:
        """
        Capture a chunk of audio from the stream
        
        Args:
            stream_url: URL of the stream
            duration: Duration of the chunk in seconds
            
        Returns:
            Audio chunk as bytes, or None if capture fails
        """
        try:
            # Create temporary file for chunk
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                temp_path = temp_file.name
            
            try:
                # Capture chunk using FFmpeg
                (
                    ffmpeg
                    .input(stream_url, t=duration)
                    .output(temp_path, acodec='pcm_s16le', ac=1, ar='16000')
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True, timeout=duration + 5)
                )
                
                # Read chunk data
                with open(temp_path, 'rb') as f:
                    chunk_data = f.read()
                
                return chunk_data
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            logger.error(f"Failed to capture chunk: {str(e)}")
            return None
    
    async def stop_stream(self, video_id: str) -> None:
        """
        Stop processing a live stream
        
        Args:
            video_id: ID of the video/stream to stop
        """
        try:
            if video_id in self.active_streams:
                task = self.active_streams[video_id]
                task.cancel()
                del self.active_streams[video_id]
                
                logger.info(f"Stream stopped for video_id: {video_id}")
            else:
                logger.warning(f"No active stream found for video_id: {video_id}")
                
        except Exception as e:
            logger.error(f"Failed to stop stream: {str(e)}")
            raise
    
    def is_stream_active(self, video_id: str) -> bool:
        """
        Check if a stream is currently active
        
        Args:
            video_id: ID of the video/stream
            
        Returns:
            True if stream is active, False otherwise
        """
        return video_id in self.active_streams


# Global instance
stream_handler = StreamHandler()
