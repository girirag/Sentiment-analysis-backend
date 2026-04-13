"""YouTube API integration for fetching trending videos"""
import os
import logging
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests

logger = logging.getLogger(__name__)


class YouTubeService:
    """Service for interacting with YouTube Data API v3"""
    
    def __init__(self):
        """Initialize YouTube API client"""
        # Try to get from environment first, then from settings
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        if not self.api_key:
            try:
                from app.config import settings
                self.api_key = settings.youtube_api_key
            except:
                pass
        
        self.youtube = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize YouTube API client"""
        try:
            if self.api_key:
                self.youtube = build('youtube', 'v3', developerKey=self.api_key)
                logger.info("YouTube API client initialized successfully")
            else:
                logger.warning("YouTube API key not found. Service will not be available.")
        except Exception as e:
            logger.error(f"Failed to initialize YouTube client: {str(e)}")
    
    def search_videos(
        self,
        query: str = "trending",
        max_results: int = 10,
        order: str = "relevance",
        region_code: str = "US"
    ) -> List[Dict[str, Any]]:
        """
        Search for videos on YouTube
        
        Args:
            query: Search query
            max_results: Maximum number of results (1-50)
            order: Sort order (relevance, date, rating, viewCount, title)
            region_code: Region code (US, GB, IN, etc.)
            
        Returns:
            List of video data
        """
        if not self.youtube:
            logger.error("YouTube client not initialized")
            return []
        
        try:
            # Search for videos
            search_response = self.youtube.search().list(
                q=query,
                part='id,snippet',
                maxResults=min(max_results, 50),
                type='video',
                order=order,
                regionCode=region_code,
                videoEmbeddable='true',
                videoSyndicated='true'
            ).execute()
            
            if not search_response.get('items'):
                logger.info("No videos found")
                return []
            
            # Get video IDs
            video_ids = [item['id']['videoId'] for item in search_response['items']]
            
            # Get detailed video information
            videos_response = self.youtube.videos().list(
                part='snippet,contentDetails,statistics',
                id=','.join(video_ids)
            ).execute()
            
            # Process videos
            results = []
            for video in videos_response.get('items', []):
                results.append(self._format_video_data(video))
            
            logger.info(f"Found {len(results)} videos from YouTube")
            return results
            
        except HttpError as e:
            logger.error(f"YouTube API error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error searching YouTube: {str(e)}")
            return []
    
    def get_trending_videos(
        self,
        max_results: int = 10,
        region_code: str = "US",
        category_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get trending videos from YouTube
        
        Args:
            max_results: Maximum number of results
            region_code: Region code
            category_id: Video category ID (optional)
            
        Returns:
            List of trending videos
        """
        if not self.youtube:
            logger.error("YouTube client not initialized")
            return []
        
        try:
            params = {
                'part': 'snippet,contentDetails,statistics',
                'chart': 'mostPopular',
                'maxResults': min(max_results, 50),
                'regionCode': region_code
            }
            
            if category_id:
                params['videoCategoryId'] = category_id
            
            response = self.youtube.videos().list(**params).execute()
            
            results = []
            for video in response.get('items', []):
                results.append(self._format_video_data(video))
            
            logger.info(f"Found {len(results)} trending videos")
            return results
            
        except HttpError as e:
            logger.error(f"YouTube API error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting trending videos: {str(e)}")
            return []
    
    def get_channel_videos(
        self,
        channel_id: str,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get videos from a specific YouTube channel
        
        Args:
            channel_id: YouTube channel ID
            max_results: Maximum number of results
            
        Returns:
            List of videos from the channel
        """
        if not self.youtube:
            logger.error("YouTube client not initialized")
            return []
        
        try:
            # Search for videos from the channel
            search_response = self.youtube.search().list(
                channelId=channel_id,
                part='id,snippet',
                maxResults=min(max_results, 50),
                type='video',
                order='date'
            ).execute()
            
            if not search_response.get('items'):
                return []
            
            # Get video IDs
            video_ids = [item['id']['videoId'] for item in search_response['items']]
            
            # Get detailed video information
            videos_response = self.youtube.videos().list(
                part='snippet,contentDetails,statistics',
                id=','.join(video_ids)
            ).execute()
            
            results = []
            for video in videos_response.get('items', []):
                results.append(self._format_video_data(video))
            
            return results
            
        except HttpError as e:
            logger.error(f"YouTube API error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting channel videos: {str(e)}")
            return []
    
    def _format_video_data(self, video: Dict) -> Dict[str, Any]:
        """Format YouTube video data into standard format"""
        snippet = video.get('snippet', {})
        statistics = video.get('statistics', {})
        content_details = video.get('contentDetails', {})
        
        return {
            'video_id': video['id'],
            'title': snippet.get('title', ''),
            'description': snippet.get('description', ''),
            'channel': {
                'id': snippet.get('channelId', ''),
                'title': snippet.get('channelTitle', '')
            },
            'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
            'published_at': snippet.get('publishedAt', ''),
            'duration': content_details.get('duration', ''),
            'metrics': {
                'views': int(statistics.get('viewCount', 0)),
                'likes': int(statistics.get('likeCount', 0)),
                'comments': int(statistics.get('commentCount', 0))
            },
            'tags': snippet.get('tags', []),
            'category_id': snippet.get('categoryId', '')
        }
    
    def download_video(self, video_id: str, save_path: str) -> bool:
        """
        Download video using yt-dlp
        
        Args:
            video_id: YouTube video ID
            save_path: Path to save the video
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import yt_dlp
            import os
            
            logger.info(f"Downloading video {video_id} to {save_path}")
            logger.info(f"Using yt-dlp version: {yt_dlp.version.__version__}")
            
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': save_path,
                'quiet': False,
                'no_warnings': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
                
            # Verify file exists and has reasonable size
            if os.path.exists(save_path):
                file_size = os.path.getsize(save_path)
                logger.info(f"Video downloaded successfully (size: {file_size} bytes)")
                
                if file_size < 10000:  # Less than 10KB is suspicious
                    logger.error(f"Downloaded file is too small ({file_size} bytes), likely corrupted")
                    os.remove(save_path)
                    return False
                
                return True
            else:
                logger.error(f"Video file not found after download: {save_path}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to download video {video_id}: {str(e)}", exc_info=True)
            return False
    
    def get_video_categories(self, region_code: str = "US") -> List[Dict[str, Any]]:
        """
        Get available video categories for a region
        
        Args:
            region_code: Region code
            
        Returns:
            List of video categories
        """
        if not self.youtube:
            return []
        
        try:
            response = self.youtube.videoCategories().list(
                part='snippet',
                regionCode=region_code
            ).execute()
            
            categories = []
            for item in response.get('items', []):
                categories.append({
                    'id': item['id'],
                    'title': item['snippet']['title']
                })
            
            return categories
            
        except Exception as e:
            logger.error(f"Error getting categories: {str(e)}")
            return []


# Singleton instance
youtube_service = YouTubeService()
