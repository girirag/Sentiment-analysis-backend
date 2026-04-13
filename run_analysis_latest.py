import os
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import asyncio, json, time
from pathlib import Path

UPLOADS = Path("uploads")
VIDEOS_FILE = UPLOADS / "videos.json"

# Get latest video
videos = json.loads(VIDEOS_FILE.read_text())
latest = sorted(videos, key=lambda x: x["created_at"])[-1]
VIDEO_ID = latest["video_id"]
print(f"Video : {latest['title'][:70]}")
print(f"ID    : {VIDEO_ID}")
print(f"Status: {latest['status']}")

def update_status(status, error=None):
    vids = json.loads(VIDEOS_FILE.read_text())
    for v in vids:
        if v["video_id"] == VIDEO_ID:
            v["status"] = status
            if error: v["error"] = error
            break
    VIDEOS_FILE.write_text(json.dumps(vids, indent=2))
    print(f"  → status: {status}")

async def main():
    from app.services.transcriber import Transcriber
    from app.services.sentiment_analyzer import SentimentAnalyzer
    from app.services.keyword_tracker import KeywordTracker
    from app.models.schemas import AnalysisSummary

    candidates = list(UPLOADS.glob(f"{VIDEO_ID}_*.mp4"))
    if not candidates:
        print("ERROR: video file not found"); return
    video_path = str(candidates[0])
    print(f"File  : {candidates[0].name}  ({candidates[0].stat().st_size//1024//1024} MB)\n")

    update_status("processing")

    print("[1/4] Transcribing…")
    t0 = time.time()
    result = await Transcriber().transcribe_with_retry(video_path)
    print(f"  Done {time.time()-t0:.1f}s — {len(result.segments)} segs, lang={result.language}")

    print("[2/4] Sentiment (batched)…")
    t0 = time.time()
    analyzer = SentimentAnalyzer()
    timeline = await analyzer.create_timeline(result.segments)
    print(f"  Done {time.time()-t0:.1f}s — {len(timeline)} points")

    print("[3/4] Keywords…")
    t0 = time.time()
    from app.services.keyword_tracker import KeywordTracker
    tracker = KeywordTracker()
    keywords = await tracker.extract_keywords(result.text, segments=result.segments)
    keywords = await tracker.calculate_keyword_sentiment(keywords, result.segments)
    print(f"  Done {time.time()-t0:.1f}s — {len(keywords)} keywords")

    print("[4/4] Saving…")
    stats = analyzer.calculate_summary(timeline)
    analysis = {
        "video_id": VIDEO_ID,
        "video_name": candidates[0].name,
        "transcription": result.text,
        "overall_sentiment": stats["overall_sentiment"],
        "sentiment_confidence": abs(stats["avg_score"]),
        "sentiment_breakdown": {
            "positive": sum(1 for p in timeline if p.sentiment=="positive"),
            "negative": sum(1 for p in timeline if p.sentiment=="negative"),
            "total": len(timeline),
        },
        "keywords": [{"keyword": k.word, "count": k.count} for k in keywords[:20]],
        "timeline": [
            {"timestamp": p.timestamp, "sentiment": p.sentiment, "score": p.score,
             "text": next((s.text for s in result.segments if abs(s.start-p.timestamp)<10), "")}
            for p in timeline
        ],
        "summary": stats,
    }
    out = UPLOADS / f"{VIDEO_ID}_analysis.json"
    out.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
    update_status("completed")
    print(f"\n✓ Saved → {out.name}")
    print(f"  Sentiment : {stats['overall_sentiment']}  (avg {stats['avg_score']:.3f})")

asyncio.run(main())
