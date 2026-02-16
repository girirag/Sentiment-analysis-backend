"""Video processing service for audio extraction"""
import os
import tempfile
import logging
import ffmpeg
from typing import Optional

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Service for processing video files"""
    
    def __init__(self):
        """Initialize video processor"""
        self.supported_formats = {'.mp4', '.avi', '.mov', '.mkv'}
    
    def validate_video(self, file_path: str) -> bool:
        """
        Validate if the video file is valid and has audio
        
        Args:
            file_path: Path to the video file
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"Video file not found: {file_path}")
                return False
            
            # Check file extension
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in self.supported_formats:
                logger.error(f"Unsupported video format: {ext}")
                return False
            
            # Probe video file to check if it has audio
            try:
                probe = ffmpeg.probe(file_path)
                audio_streams = [stream for stream in probe['streams'] if stream['codec_type'] == 'audio']
                
                if not audio_streams:
                    logger.warning(f"Video file has no audio stream: {file_path}")
                    return False
                
                return True
                
            except ffmpeg.Error as e:
                logger.error(f"FFmpeg probe failed: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Video validation failed: {str(e)}")
            return False
    
    async def extract_audio(self, video_path: str, output_format: str = 'wav') -> str:
        """
        Extract audio from video file using FFmpeg
        
        Args:
            video_path: Path to the video file (local or Firebase Storage path)
            output_format: Output audio format (default: wav)
            
        Returns:
            Path to the extracted audio file
            
        Raises:
            ValueError: If video is invalid or has no audio
            RuntimeError: If audio extraction fails
        """
        try:
            # If it's a Firebase Storage path, download it first
            if video_path.startswith('gs://'):
                from app.services.firebase_service import firebase_service
                
                # Extract path from gs:// URL
                storage_path = video_path.replace('gs://', '').split('/', 1)[1]
                
                # Download to temporary file
                temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                temp_video.close()
                
                await firebase_service.download_file(storage_path, temp_video.name)
                video_path = temp_video.name
            
            # Validate video
            if not self.validate_video(video_path):
                raise ValueError("Invalid video file or no audio stream found")
            
            # Create temporary file for audio output
            audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{output_format}')
            audio_file.close()
            audio_path = audio_file.name
            
            logger.info(f"Extracting audio from: {video_path}")
            
            # Extract audio using FFmpeg
            try:
                (
                    ffmpeg
                    .input(video_path)
                    .output(audio_path, acodec='pcm_s16le', ac=1, ar='16000')
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
                
                logger.info(f"Audio extracted successfully: {audio_path}")
                return audio_path
                
            except ffmpeg.Error as e:
                logger.error(f"FFmpeg error: {e.stderr.decode()}")
                # Clean up audio file if extraction failed
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                raise RuntimeError(f"Audio extraction failed: {e.stderr.decode()}")
                
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Audio extraction failed: {str(e)}")
            raise RuntimeError(f"Audio extraction failed: {str(e)}")
    
    def get_video_duration(self, video_path: str) -> float:
        """
        Get the duration of a video file in seconds
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Duration in seconds
        """
        try:
            probe = ffmpeg.probe(video_path)
            duration = float(probe['format']['duration'])
            return duration
            
        except Exception as e:
            logger.error(f"Failed to get video duration: {str(e)}")
            return 0.0
    
    def get_video_info(self, video_path: str) -> dict:
        """
        Get detailed information about a video file
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Dictionary with video information
        """
        try:
            probe = ffmpeg.probe(video_path)
            
            video_info = {
                'duration': float(probe['format']['duration']),
                'size': int(probe['format']['size']),
                'bit_rate': int(probe['format']['bit_rate']),
                'format_name': probe['format']['format_name'],
            }
            
            # Get video stream info
            video_streams = [s for s in probe['streams'] if s['codec_type'] == 'video']
            if video_streams:
                video_stream = video_streams[0]
                video_info['width'] = video_stream.get('width', 0)
                video_info['height'] = video_stream.get('height', 0)
                video_info['codec'] = video_stream.get('codec_name', 'unknown')
            
            # Get audio stream info
            audio_streams = [s for s in probe['streams'] if s['codec_type'] == 'audio']
            if audio_streams:
                audio_stream = audio_streams[0]
                video_info['audio_codec'] = audio_stream.get('codec_name', 'unknown')
                video_info['sample_rate'] = audio_stream.get('sample_rate', 0)
                video_info['channels'] = audio_stream.get('channels', 0)
            
            return video_info
            
        except Exception as e:
            logger.error(f"Failed to get video info: {str(e)}")
            return {}
