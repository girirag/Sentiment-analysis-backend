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
                # Try to get credentials from environment variable first (for Render/cloud deployment)
                firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS")
                
                if firebase_creds_json:
                    # Parse JSON from environment variable
                    import json
                    cred_dict = json.loads(firebase_creds_json)
                    cred = credentials.Certificate(cred_dict)
                    logger.info("Using Firebase credentials from environment variable")
                else:
                    # Fall back to file path
                    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "./firebase-key.json")
                    
                    if not os.path.exists(cred_path):
                        logger.warning(f"Firebase credentials not found at {cred_path}. Firebase features will be disabled.")
                        # Don't initialize Firebase if credentials are missing
                        self.db = None
                        self.bucket = None
                        return
                    
                    cred = credentials.Certificate(cred_path)
                    logger.info(f"Using Firebase credentials from file: {cred_path}")
                
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
    
    # ==================== Clip Jobs Operations ====================

    async def create_clip_job(
        self,
        job_id: str,
        video_id: str,
        user_id: str,
        similarity_threshold: float,
    ) -> None:
        """
        Create a new clip job document in Firestore

        Args:
            job_id: Unique job identifier (UUID)
            video_id: The ID of the video being processed
            user_id: The ID of the user who initiated the job
            similarity_threshold: Minimum similarity score for matches
        """
        try:
            doc_data = {
                "job_id": job_id,
                "video_id": video_id,
                "user_id": user_id,
                "status": "queued",
                "similarity_threshold": similarity_threshold,
                "clip_ids": [],
                "error": None,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
            self.db.collection("clip_jobs").document(job_id).set(doc_data)
            logger.info(f"Created clip job: {job_id}")
        except Exception as e:
            logger.error(f"Failed to create clip job: {str(e)}")
            raise

    async def update_clip_job(self, job_id: str, updates: Dict[str, Any]) -> None:
        """
        Update fields on a clip job document

        Args:
            job_id: The clip job ID
            updates: Dictionary of fields to update (e.g. status, clip_ids, error)
        """
        try:
            updates["updated_at"] = firestore.SERVER_TIMESTAMP
            self.db.collection("clip_jobs").document(job_id).update(updates)
            logger.info(f"Updated clip job {job_id}: {list(updates.keys())}")
        except Exception as e:
            logger.error(f"Failed to update clip job: {str(e)}")
            raise

    async def get_clip_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a clip job document from Firestore

        Args:
            job_id: The clip job ID

        Returns:
            Clip job data dictionary or None if not found
        """
        try:
            doc = self.db.collection("clip_jobs").document(job_id).get()
            if doc.exists:
                return doc.to_dict()
            logger.warning(f"Clip job not found: {job_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to get clip job: {str(e)}")
            raise

    # ==================== Clip Results Operations ====================

    async def create_clip_result(self, clip_result: Dict[str, Any]) -> None:
        """
        Create a clip result document in Firestore using clip_id as the document ID

        Args:
            clip_result: Dictionary containing clip result fields (must include 'clip_id')
        """
        try:
            clip_id = clip_result["clip_id"]
            doc_data = dict(clip_result)
            doc_data["created_at"] = firestore.SERVER_TIMESTAMP
            self.db.collection("clip_results").document(clip_id).set(doc_data)
            logger.info(f"Created clip result: {clip_id}")
        except Exception as e:
            logger.error(f"Failed to create clip result: {str(e)}")
            raise

    async def get_clip_results_for_video(self, video_id: str) -> List[Dict[str, Any]]:
        """
        Get all clip results for a video, ordered by start_time ascending

        Args:
            video_id: The video ID

        Returns:
            List of clip result documents ordered by start_time
        """
        try:
            query = (
                self.db.collection("clip_results")
                .where("video_id", "==", video_id)
                .order_by("start_time")
            )
            docs = query.stream()
            results = []
            for doc in docs:
                data = doc.to_dict()
                results.append(data)
            return results
        except Exception as e:
            logger.error(f"Failed to get clip results for video {video_id}: {str(e)}")
            raise

    async def get_clip_result(self, clip_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single clip result document from Firestore

        Args:
            clip_id: The clip ID

        Returns:
            Clip result data dictionary or None if not found
        """
        try:
            doc = self.db.collection("clip_results").document(clip_id).get()
            if doc.exists:
                return doc.to_dict()
            logger.warning(f"Clip result not found: {clip_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to get clip result: {str(e)}")
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
