"""Twitter API integration for fetching trending videos"""
import tweepy
import requests
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class TwitterService:
    """Service for interacting with Twitter API to fetch trending videos"""
    
    def __init__(self):
        """Initialize Twitter API client"""
        self.api_key = os.getenv("TWITTER_API_KEY")
        self.api_secret = os.getenv("TWITTER_API_SECRET")
        self.bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        self.access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        self.access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Tweepy client with credentials"""
        try:
            if self.bearer_token:
                # Twitter API v2 client
                self.client = tweepy.Client(
                    bearer_token=self.bearer_token,
                    consumer_key=self.api_key,
                    consumer_secret=self.api_secret,
                    access_token=self.access_token,
                    access_token_secret=self.access_token_secret,
                    wait_on_rate_limit=True
                )
                logger.info("Twitter API client initialized successfully")
            else:
                logger.warning("Twitter API credentials not found. Service will not be available.")
        except Exception as e:
            logger.error(f"Failed to initialize Twitter client: {str(e)}")
    
    def search_trending_videos(
        self, 
        query: str = "video", 
        max_results: int = 10,
        language: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Search for trending tweets with videos
        
        Args:
            query: Search query (default: "video")
            max_results: Maximum number of results (10-100)
            language: Language code (default: "en")
            
        Returns:
            List of tweet data with video information
        """
        if not self.client:
            logger.error("Twitter client not initialized")
            return []
        
        try:
            # Search for tweets with videos
            search_query = f"{query} has:videos -is:retweet lang:{language}"
            
            tweets = self.client.search_recent_tweets(
                query=search_query,
                max_results=min(max_results, 100),
                tweet_fields=['created_at', 'public_metrics', 'author_id', 'entities'],
                expansions=['attachments.media_keys', 'author_id'],
                media_fields=['url', 'preview_image_url', 'variants', 'duration_ms', 'type']
            )
            
            if not tweets.data:
                logger.info("No tweets found")
                return []
            
            # Process tweets and extract video information
            results = []
            media_dict = {media.media_key: media for media in tweets.includes.get('media', [])}
            users_dict = {user.id: user for user in tweets.includes.get('users', [])}
            
            for tweet in tweets.data:
                if hasattr(tweet, 'attachments') and tweet.attachments:
                    media_keys = tweet.attachments.get('media_keys', [])
                    
                    for media_key in media_keys:
                        media = media_dict.get(media_key)
                        
                        if media and media.type == 'video':
                            author = users_dict.get(tweet.author_id)
                            
                            # Get the highest quality video variant
                            video_url = self._get_best_video_variant(media)
                            
                            if video_url:
                                results.append({
                                    'tweet_id': tweet.id,
                                    'text': tweet.text,
                                    'author': {
                                        'id': author.id if author else None,
                                        'username': author.username if author else None,
                                        'name': author.name if author else None
                                    },
                                    'video_url': video_url,
                                    'thumbnail_url': media.preview_image_url,
                                    'duration_ms': media.duration_ms,
                                    'created_at': tweet.created_at.isoformat() if tweet.created_at else None,
                                    'metrics': {
                                        'likes': tweet.public_metrics.get('like_count', 0),
                                        'retweets': tweet.public_metrics.get('retweet_count', 0),
                                        'replies': tweet.public_metrics.get('reply_count', 0),
                                        'views': tweet.public_metrics.get('impression_count', 0)
                                    }
                                })
            
            logger.info(f"Found {len(results)} videos from Twitter")
            return results
            
        except Exception as e:
            logger.error(f"Error searching Twitter for videos: {str(e)}")
            return []
    
    def _get_best_video_variant(self, media) -> Optional[str]:
        """
        Get the highest quality video URL from media variants
        
        Args:
            media: Media object from Twitter API
            
        Returns:
            URL of the best quality video
        """
        if not hasattr(media, 'variants') or not media.variants:
            return None
        
        # Filter for mp4 videos and sort by bitrate
        mp4_variants = [
            v for v in media.variants 
            if hasattr(v, 'content_type') and v.content_type == 'video/mp4'
        ]
        
        if not mp4_variants:
            return None
        
        # Sort by bitrate (highest first)
        mp4_variants.sort(
            key=lambda v: v.bit_rate if hasattr(v, 'bit_rate') and v.bit_rate else 0,
            reverse=True
        )
        
        return mp4_variants[0].url if mp4_variants else None
    
    def get_trending_topics(self, woeid: int = 1) -> List[Dict[str, Any]]:
        """
        Get trending topics (requires API v1.1)
        
        Args:
            woeid: Where On Earth ID (1 = worldwide)
            
        Returns:
            List of trending topics
        """
        # Note: This requires API v1.1 which needs different authentication
        # For now, return empty list
        logger.warning("Trending topics require Twitter API v1.1 - not implemented yet")
        return []
    
    def download_video(self, video_url: str, save_path: str) -> bool:
        """
        Download video from Twitter URL
        
        Args:
            video_url: URL of the video
            save_path: Path to save the video
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Video downloaded successfully to {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download video: {str(e)}")
            return False
    
    def search_by_hashtag(self, hashtag: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for videos by hashtag
        
        Args:
            hashtag: Hashtag to search (without #)
            max_results: Maximum number of results
            
        Returns:
            List of tweet data with video information
        """
        query = f"#{hashtag}"
        return self.search_trending_videos(query=query, max_results=max_results)
    
    def search_by_user(self, username: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for videos from a specific user
        
        Args:
            username: Twitter username (without @)
            max_results: Maximum number of results
            
        Returns:
            List of tweet data with video information
        """
        if not self.client:
            logger.error("Twitter client not initialized")
            return []
        
        try:
            # Get user ID
            user = self.client.get_user(username=username)
            if not user.data:
                logger.error(f"User {username} not found")
                return []
            
            user_id = user.data.id
            
            # Get user's tweets with videos
            tweets = self.client.get_users_tweets(
                id=user_id,
                max_results=max_results,
                tweet_fields=['created_at', 'public_metrics', 'entities'],
                expansions=['attachments.media_keys'],
                media_fields=['url', 'preview_image_url', 'variants', 'duration_ms', 'type']
            )
            
            if not tweets.data:
                return []
            
            # Process tweets similar to search_trending_videos
            results = []
            media_dict = {media.media_key: media for media in tweets.includes.get('media', [])}
            
            for tweet in tweets.data:
                if hasattr(tweet, 'attachments') and tweet.attachments:
                    media_keys = tweet.attachments.get('media_keys', [])
                    
                    for media_key in media_keys:
                        media = media_dict.get(media_key)
                        
                        if media and media.type == 'video':
                            video_url = self._get_best_video_variant(media)
                            
                            if video_url:
                                results.append({
                                    'tweet_id': tweet.id,
                                    'text': tweet.text,
                                    'author': {
                                        'id': user_id,
                                        'username': username,
                                        'name': user.data.name
                                    },
                                    'video_url': video_url,
                                    'thumbnail_url': media.preview_image_url,
                                    'duration_ms': media.duration_ms,
                                    'created_at': tweet.created_at.isoformat() if tweet.created_at else None,
                                    'metrics': {
                                        'likes': tweet.public_metrics.get('like_count', 0),
                                        'retweets': tweet.public_metrics.get('retweet_count', 0),
                                        'replies': tweet.public_metrics.get('reply_count', 0),
                                        'views': tweet.public_metrics.get('impression_count', 0)
                                    }
                                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error fetching videos from user {username}: {str(e)}")
            return []


# Singleton instance
twitter_service = TwitterService()
