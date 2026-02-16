"""Firebase service for Firestore and Storage operations"""
import os
from typing import Optional, Dict, Any, List
import firebase_admin
from firebase_admin import credentials, firestore, storage, auth
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FirebaseService:
    """Service for interacting with Firebase (Firestore, Storage, Auth)"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """Singleton pattern to ensure only one Firebase instance"""
        if cls._instance is None:
            cls._instance = super(FirebaseService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize Firebase Admin SDK"""
        if not self._initialized:
            self._initialize_firebase()
            self._initialized = True
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK with credentials"""
        try:
            # Check if already initialized
            if not firebase_admin._apps:
                cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "./firebase-key.json")
                
                if not os.path.exists(cred_path):
                    logger.warning(f"Firebase credentials not found at {cred_path}. Firebase features will be disabled.")
                    # Don't initialize Firebase if credentials are missing
                    self.db = None
                    self.bucket = None
                    return
                
                cred = credentials.Certificate(cred_path)
                
                firebase_admin.initialize_app(cred, {
                    'storageBucket': os.getenv("FIREBASE_STORAGE_BUCKET")
                })
                
                logger.info("Firebase Admin SDK initialized successfully")
            
            self.db = firestore.client()
            self.bucket = storage.bucket()
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            # Set to None instead of raising to allow app to start
            self.db = None
            self.bucket = None
    
    # ==================== Firestore Operations ====================
    
    async def create_video(self, video_data: Dict[str, Any]) -> str:
        """
        Create a new video document in Firestore
        
        Args:
            video_data: Dictionary containing video metadata
            
        Returns:
            video_id: The ID of the created video document
        """
        try:
            # Add timestamps
            video_data['createdAt'] = firestore.SERVER_TIMESTAMP
            video_data['updatedAt'] = firestore.SERVER_TIMESTAMP
            
            # Create document with auto-generated ID
            doc_ref = self.db.collection('videos').document()
            doc_ref.set(video_data)
            
            logger.info(f"Created video document: {doc_ref.id}")
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"Failed to create video document: {str(e)}")
            raise
    
    async def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a video document from Firestore
        
        Args:
            video_id: The ID of the video document
            
        Returns:
            Video data dictionary or None if not found
        """
        try:
            doc_ref = self.db.collection('videos').document(video_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            else:
                logger.warning(f"Video document not found: {video_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get video document: {str(e)}")
            raise
    
    async def update_video_status(self, video_id: str, status: str, error: Optional[str] = None) -> None:
        """
        Update the status of a video document
        
        Args:
            video_id: The ID of the video document
            status: New status (queued, processing, completed, failed)
            error: Optional error message if status is failed
        """
        try:
            doc_ref = self.db.collection('videos').document(video_id)
            
            update_data = {
                'status': status,
                'updatedAt': firestore.SERVER_TIMESTAMP
            }
            
            if error:
                update_data['error'] = error
            
            doc_ref.update(update_data)
            logger.info(f"Updated video {video_id} status to: {status}")
            
        except Exception as e:
            logger.error(f"Failed to update video status: {str(e)}")
            raise
    
    async def create_analysis(self, analysis_data: Dict[str, Any]) -> str:
        """
        Create a new analysis document in Firestore
        
        Args:
            analysis_data: Dictionary containing analysis results
            
        Returns:
            analysis_id: The ID of the created analysis document
        """
        try:
            # Add timestamp
            analysis_data['createdAt'] = firestore.SERVER_TIMESTAMP
            
            # Create document with auto-generated ID
            doc_ref = self.db.collection('analysis').document()
            doc_ref.set(analysis_data)
            
            logger.info(f"Created analysis document: {doc_ref.id}")
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"Failed to create analysis document: {str(e)}")
            raise
    
    async def get_analysis(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get analysis results for a video
        
        Args:
            video_id: The ID of the video
            
        Returns:
            Analysis data dictionary or None if not found
        """
        try:
            # Query analysis collection by videoId
            query = self.db.collection('analysis').where('videoId', '==', video_id).limit(1)
            docs = query.stream()
            
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            
            logger.warning(f"Analysis not found for video: {video_id}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get analysis: {str(e)}")
            raise
    
    async def get_videos_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get all videos for a specific user
        
        Args:
            user_id: The user ID
            limit: Maximum number of videos to return
            
        Returns:
            List of video documents
        """
        try:
            query = self.db.collection('videos').where('userId', '==', user_id).limit(limit)
            docs = query.stream()
            
            videos = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                videos.append(data)
            
            return videos
            
        except Exception as e:
            logger.error(f"Failed to get videos for user: {str(e)}")
            raise
    
    # ==================== Firebase Storage Operations ====================
    
    async def upload_file(self, file_path: str, destination: str) -> str:
        """
        Upload a file to Firebase Storage
        
        Args:
            file_path: Local path to the file
            destination: Destination path in Firebase Storage
            
        Returns:
            Public URL of the uploaded file
        """
        try:
            blob = self.bucket.blob(destination)
            blob.upload_from_filename(file_path)
            
            # Make the blob publicly accessible (optional, configure based on requirements)
            # blob.make_public()
            
            logger.info(f"Uploaded file to: {destination}")
            return f"gs://{self.bucket.name}/{destination}"
            
        except Exception as e:
            logger.error(f"Failed to upload file: {str(e)}")
            raise
    
    async def download_file(self, source: str, destination: str) -> None:
        """
        Download a file from Firebase Storage
        
        Args:
            source: Source path in Firebase Storage
            destination: Local destination path
        """
        try:
            blob = self.bucket.blob(source)
            blob.download_to_filename(destination)
            
            logger.info(f"Downloaded file from: {source}")
            
        except Exception as e:
            logger.error(f"Failed to download file: {str(e)}")
            raise
    
    async def delete_file(self, file_path: str) -> None:
        """
        Delete a file from Firebase Storage
        
        Args:
            file_path: Path to the file in Firebase Storage
        """
        try:
            blob = self.bucket.blob(file_path)
            blob.delete()
            
            logger.info(f"Deleted file: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to delete file: {str(e)}")
            raise
    
    async def get_file_url(self, file_path: str, expiration: int = 3600) -> str:
        """
        Get a signed URL for a file in Firebase Storage
        
        Args:
            file_path: Path to the file in Firebase Storage
            expiration: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Signed URL for the file
        """
        try:
            blob = self.bucket.blob(file_path)
            url = blob.generate_signed_url(expiration=expiration)
            
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate signed URL: {str(e)}")
            raise
    
    # ==================== Authentication Operations ====================
    
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a Firebase authentication token
        
        Args:
            token: Firebase ID token
            
        Returns:
            Decoded token containing user information
            
        Raises:
            ValueError: If token is invalid
        """
        try:
            decoded_token = auth.verify_id_token(token)
            
            user_info = {
                'uid': decoded_token['uid'],
                'email': decoded_token.get('email'),
                'email_verified': decoded_token.get('email_verified', False),
                'name': decoded_token.get('name'),
            }
            
            logger.info(f"Token verified for user: {user_info['uid']}")
            return user_info
            
        except auth.InvalidIdTokenError:
            logger.error("Invalid Firebase ID token")
            raise ValueError("Invalid authentication token")
        except auth.ExpiredIdTokenError:
            logger.error("Expired Firebase ID token")
            raise ValueError("Authentication token has expired")
        except Exception as e:
            logger.error(f"Failed to verify token: {str(e)}")
            raise ValueError("Failed to verify authentication token")
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user information from Firebase Auth
        
        Args:
            user_id: The user ID (UID)
            
        Returns:
            User information dictionary or None if not found
        """
        try:
            user = auth.get_user(user_id)
            
            user_info = {
                'uid': user.uid,
                'email': user.email,
                'email_verified': user.email_verified,
                'display_name': user.display_name,
                'photo_url': user.photo_url,
                'disabled': user.disabled,
            }
            
            return user_info
            
        except auth.UserNotFoundError:
            logger.warning(f"User not found: {user_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to get user: {str(e)}")
            raise


# Global instance
firebase_service = FirebaseService()
