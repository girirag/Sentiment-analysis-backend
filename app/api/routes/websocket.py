from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Set
import asyncio
import json
from app.services.firebase_service import FirebaseService

router = APIRouter()

# Store active WebSocket connections
active_connections: Dict[str, Set[WebSocket]] = {}

firebase_service = FirebaseService()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.stream_data: Dict[str, list] = {}  # Store stream chunks data
    
    async def connect(self, websocket: WebSocket, video_id: str):
        await websocket.accept()
        if video_id not in self.active_connections:
            self.active_connections[video_id] = set()
            self.stream_data[video_id] = []
        self.active_connections[video_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, video_id: str):
        if video_id in self.active_connections:
            self.active_connections[video_id].discard(websocket)
            if not self.active_connections[video_id]:
                del self.active_connections[video_id]
                # Clean up stream data after all connections close
                if video_id in self.stream_data:
                    del self.stream_data[video_id]
    
    async def send_update(self, video_id: str, message: dict):
        if video_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[video_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.add(connection)
            
            # Remove disconnected clients
            for connection in disconnected:
                self.active_connections[video_id].discard(connection)
    
    async def broadcast(self, video_id: str, message: dict):
        await self.send_update(video_id, message)
    
    def add_stream_chunk(self, video_id: str, chunk_data: dict):
        """Add processed chunk data to stream"""
        if video_id not in self.stream_data:
            self.stream_data[video_id] = []
        self.stream_data[video_id].append(chunk_data)
    
    def get_stream_data(self, video_id: str) -> list:
        """Get all stream chunks data"""
        return self.stream_data.get(video_id, [])


manager = ConnectionManager()


@router.websocket("/ws/analysis/{video_id}")
async def websocket_endpoint(websocket: WebSocket, video_id: str):
    """
    WebSocket endpoint for real-time analysis updates.
    
    Sends updates every 2 seconds during processing.
    Sends completion notification when processing finishes.
    """
    await manager.connect(websocket, video_id)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "video_id": video_id,
            "message": "Connected to analysis updates"
        })
        
        # Start monitoring the video status
        while True:
            try:
                # Check video status from Firestore
                video_data = firebase_service.get_video(video_id)
                
                if not video_data:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Video not found"
                    })
                    break
                
                status = video_data.get("status", "unknown")
                
                # Send status update
                await websocket.send_json({
                    "type": "status_update",
                    "video_id": video_id,
                    "status": status,
                    "timestamp": video_data.get("updated_at")
                })
                
                # If processing is complete or failed, send final notification
                if status in ["completed", "failed"]:
                    # Get analysis data if completed
                    if status == "completed":
                        analysis = firebase_service.get_analysis(video_id)
                        await websocket.send_json({
                            "type": "completion",
                            "video_id": video_id,
                            "status": status,
                            "analysis": analysis
                        })
                    else:
                        await websocket.send_json({
                            "type": "completion",
                            "video_id": video_id,
                            "status": status,
                            "error": video_data.get("error")
                        })
                    break
                
                # Wait 2 seconds before next update
                await asyncio.sleep(2)
                
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
                break
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, video_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, video_id)


async def notify_analysis_update(video_id: str, update_data: dict):
    """
    Helper function to send updates to all connected clients for a video.
    Can be called from Celery tasks.
    """
    await manager.broadcast(video_id, {
        "type": "analysis_update",
        "video_id": video_id,
        "data": update_data
    })


@router.websocket("/ws/stream/{video_id}")
async def stream_websocket_endpoint(websocket: WebSocket, video_id: str):
    """
    WebSocket endpoint for live stream analysis updates.
    
    Sends real-time updates as stream chunks are processed.
    """
    await manager.connect(websocket, video_id)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "video_id": video_id,
            "message": "Connected to live stream analysis"
        })
        
        # Keep connection alive and listen for messages
        while True:
            try:
                # Wait for messages from client or timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                
                # Handle client messages
                try:
                    message = json.loads(data)
                    
                    if message.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif message.get("type") == "get_data":
                        # Send all accumulated stream data
                        stream_data = manager.get_stream_data(video_id)
                        await websocket.send_json({
                            "type": "stream_data",
                            "video_id": video_id,
                            "chunks": stream_data
                        })
                    
                except json.JSONDecodeError:
                    pass
                
            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({"type": "keepalive"})
                except:
                    break
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, video_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, video_id)
    finally:
        manager.disconnect(websocket, video_id)


async def notify_stream_chunk(video_id: str, chunk_data: dict):
    """
    Send live stream chunk update to all connected clients.
    Called when a new chunk is processed.
    """
    # Store chunk data
    manager.add_stream_chunk(video_id, chunk_data)
    
    # Broadcast to all connected clients
    await manager.broadcast(video_id, {
        "type": "chunk_update",
        "video_id": video_id,
        "chunk": chunk_data
    })
