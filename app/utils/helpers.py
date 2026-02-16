"""Helper utility functions"""
import uuid
from datetime import datetime

def generate_id() -> str:
    """Generate a unique ID"""
    return str(uuid.uuid4())

def get_timestamp() -> str:
    """Get current timestamp in ISO format"""
    return datetime.utcnow().isoformat()
