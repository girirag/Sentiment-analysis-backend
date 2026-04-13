import json
from pathlib import Path

f = Path("uploads/videos.json")
videos = json.loads(f.read_text())
before = len(videos)
videos = [v for v in videos if v["video_id"] != "50631664-0eb4-4781-a1ca-824902a4f8c8"]
f.write_text(json.dumps(videos, indent=2))
print(f"Removed {before - len(videos)} entry. {len(videos)} videos remain.")
