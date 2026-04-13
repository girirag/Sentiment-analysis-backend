"""
Directly run analysis on the stuck video, bypassing Celery.
Uses the faster batched sentiment pipeline.
"""
import os
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import asyncio, json, time
from pathlib import Path

VIDEO_ID = "39d9f073-7a79-4cea-a9bd-bd59a49509b9"
UPLOADS = Path("uploads")
VIDEOS_FILE = UPLOADS / "videos.json"

def update_status(status, error=None):
    with open(VIDEOS_FILE) as f:
        videos = json.load(f)
    for v in videos:
        if v["video_id"] == VIDEO_ID:
            v["status"] = status
            if error:
                v["error"] = error
            break
    with open(VIDEOS_FILE, "w") as f:
        json.dump(videos, f, indent=2)
    print(f"  → status: {status}")

async def main():
    from app.services.transcriber import Transcriber
    from app.services.sentiment_analyzer import SentimentAnalyzer
    from app.services.keyword_tracker import KeywordTracker
    from app.models.schemas import AnalysisSummary

    # Find video file
    candidates = list(UPLOADS.glob(f"{VIDEO_ID}_*.mp4"))
    if not candidates:
        print("ERROR: video file not found"); return
    video_path = str(candidates[0])
    print(f"Video: {candidates[0].name}")

    update_status("processing")

    # ── Step 1: Transcribe ────────────────────────────────────────────
    print("\n[1/4] Transcribing (Whisper base)…")
    t0 = time.time()
    transcriber = Transcriber()
    result = await transcriber.transcribe_with_retry(video_path)
    print(f"  Done in {time.time()-t0:.1f}s — {len(result.segments)} segments, lang={result.language}")

    # ── Step 2: Sentiment (batched) ───────────────────────────────────
    print("\n[2/4] Sentiment analysis (batched)…")
    t0 = time.time()
    analyzer = SentimentAnalyzer()
    timeline = await analyzer.create_timeline(result.segments)
    print(f"  Done in {time.time()-t0:.1f}s — {len(timeline)} timeline points")

    # ── Step 3: Keywords ──────────────────────────────────────────────
    print("\n[3/4] Extracting keywords…")
    t0 = time.time()
    tracker = KeywordTracker()
    keywords = await tracker.extract_keywords(result.text, segments=result.segments)
    keywords = await tracker.calculate_keyword_sentiment(keywords, result.segments)
    print(f"  Done in {time.time()-t0:.1f}s — {len(keywords)} keywords")

    # ── Step 4: Save ──────────────────────────────────────────────────
    print("\n[4/4] Saving analysis…")
    summary_stats = analyzer.calculate_summary(timeline)
    duration = timeline[-1].timestamp if timeline else 0

    analysis = {
        "video_id": VIDEO_ID,
        "video_name": candidates[0].name,
        "transcription": result.text,
        "overall_sentiment": summary_stats["overall_sentiment"],
        "sentiment_confidence": abs(summary_stats["avg_score"]),
        "sentiment_breakdown": {
            "positive": sum(1 for p in timeline if p.sentiment == "positive"),
            "negative": sum(1 for p in timeline if p.sentiment == "negative"),
            "total": len(timeline),
        },
        "keywords": [{"keyword": k.word, "count": k.count} for k in keywords[:20]],
        "timeline": [
            {"timestamp": p.timestamp, "sentiment": p.sentiment, "score": p.score,
             "text": next((s.text for s in result.segments if abs(s.start - p.timestamp) < 10), "")}
            for p in timeline
        ],
        "summary": summary_stats,
    }

    out_path = UPLOADS / f"{VIDEO_ID}_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    update_status("completed")
    print(f"\n✓ Analysis saved → {out_path.name}")
    print(f"  Overall sentiment : {summary_stats['overall_sentiment']}")
    print(f"  Avg score         : {summary_stats['avg_score']:.3f}")

asyncio.run(main())
