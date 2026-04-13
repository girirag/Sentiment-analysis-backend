"""
End-to-end test of the video clip highlights pipeline using:
  - Dataset:  uploads/sample_dataset.json  (Tamil Nadu elections 2026)
  - Video:    uploads/24706ca8-..._youtube_HW5VC08tNMw.mp4
  - Analysis: uploads/24706ca8-..._analysis.json

Runs entirely locally — no Firebase, no Celery.
Clips are written to uploads/test_clips/.
"""
import os
# Force PyTorch-only mode — avoids the TF/protobuf version conflict
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import json
import sys
import time
from pathlib import Path

# ── resolve paths ──────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent
UPLOADS_DIR = BACKEND_DIR / "uploads"
DATASET_PATH = UPLOADS_DIR / "sample_dataset.json"
VIDEO_ID = "24706ca8-e86d-4b54-91b5-dfbab6c6797e"
ANALYSIS_PATH = UPLOADS_DIR / f"{VIDEO_ID}_analysis.json"
VIDEO_PATH = next(UPLOADS_DIR.glob(f"{VIDEO_ID}_*.mp4"), None)
OUTPUT_DIR = UPLOADS_DIR / "test_clips"
OUTPUT_DIR.mkdir(exist_ok=True)

SIMILARITY_THRESHOLD = 0.25   # lower threshold — dataset is Tamil Nadu politics, video is Iran/Dubai news

# ── imports ────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(BACKEND_DIR))
from app.services.dataset_parser import DatasetParser
from app.services.semantic_matcher import SemanticMatcher
from app.services.clip_extractor import ClipExtractor, ClipExtractionError

# ── helpers ────────────────────────────────────────────────────────────────────
def fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"

def separator(title: str = "") -> None:
    print("\n" + "─" * 60)
    if title:
        print(f"  {title}")
        print("─" * 60)

# ══════════════════════════════════════════════════════════════════════════════
separator("STEP 1 — Parse dataset")
# ══════════════════════════════════════════════════════════════════════════════
t0 = time.time()
parser = DatasetParser()
with open(DATASET_PATH, "rb") as f:
    dataset_entries = parser.parse(f.read(), DATASET_PATH.name)

print(f"  Parsed {len(dataset_entries)} entries in {time.time()-t0:.2f}s")
for i, e in enumerate(dataset_entries[:3], 1):
    print(f"  [{i}] {e[:100]}…")
print(f"  … and {len(dataset_entries)-3} more")

# ══════════════════════════════════════════════════════════════════════════════
separator("STEP 2 — Load transcript segments")
# ══════════════════════════════════════════════════════════════════════════════
with open(ANALYSIS_PATH, "r", encoding="utf-8") as f:
    analysis = json.load(f)

raw_timeline = analysis.get("timeline", [])
segments = []
for i, seg in enumerate(raw_timeline):
    start = float(seg.get("timestamp", 0.0))
    if i + 1 < len(raw_timeline):
        end = float(raw_timeline[i + 1]["timestamp"])
    else:
        end = start + 10.0   # last segment: assume 10 s
    segments.append({
        "text": seg.get("text", ""),
        "start": start,
        "end": end,
        "original_language": seg.get("original_language", ""),
        "translated_text": seg.get("translated_text", ""),
    })

print(f"  Loaded {len(segments)} transcript segments")
for s in segments[:3]:
    print(f"  [{fmt(s['start'])}–{fmt(s['end'])}] {s['text'][:80]}…")

# ══════════════════════════════════════════════════════════════════════════════
separator("STEP 3 — Semantic matching")
# ══════════════════════════════════════════════════════════════════════════════
print(f"  Loading sentence-transformers model…")
t0 = time.time()
matcher = SemanticMatcher()
matches = matcher.match(dataset_entries, segments, threshold=SIMILARITY_THRESHOLD)
print(f"  Matching done in {time.time()-t0:.2f}s")
print(f"  Found {len(matches)} match(es) above threshold {SIMILARITY_THRESHOLD}")

if not matches:
    print("\n  ⚠  No matches found. The dataset is Tamil Nadu politics; the video is")
    print("     Iran/Dubai news — semantic overlap is expected to be low.")
    print("     Try a video whose content relates to Tamil Nadu / Indian politics.")
    sys.exit(0)

for m in matches:
    seg = m.segment
    print(f"\n  score={m.similarity_score:.3f}  [{fmt(seg['start'])}–{fmt(seg['end'])}]")
    print(f"    transcript : {seg['text'][:90]}")
    print(f"    dataset    : {m.dataset_entry[:90]}")

# ══════════════════════════════════════════════════════════════════════════════
separator("STEP 4 — Extract clips with FFmpeg")
# ══════════════════════════════════════════════════════════════════════════════
if VIDEO_PATH is None:
    print(f"  ✗ Video file not found for {VIDEO_ID}. Skipping FFmpeg step.")
    sys.exit(0)

video_duration = segments[-1]["end"] if segments else 60.0
extractor = ClipExtractor()
produced = []

for i, m in enumerate(matches, 1):
    seg = m.segment
    clip_path = OUTPUT_DIR / f"clip_{i:02d}_{fmt(seg['start']).replace(':','m')}s.mp4"
    print(f"\n  [{i}/{len(matches)}] Extracting {fmt(seg['start'])}–{fmt(seg['end'])}  →  {clip_path.name}")
    try:
        extractor.extract(
            video_path=str(VIDEO_PATH),
            start=seg["start"],
            end=seg["end"],
            output_path=str(clip_path),
            video_duration=video_duration,
        )
        size_kb = clip_path.stat().st_size // 1024
        print(f"       ✓  {size_kb} KB written")
        produced.append(clip_path)
    except ClipExtractionError as e:
        print(f"       ✗  FFmpeg error (skipped): {e}")

# ══════════════════════════════════════════════════════════════════════════════
separator("SUMMARY")
# ══════════════════════════════════════════════════════════════════════════════
print(f"  Dataset entries  : {len(dataset_entries)}")
print(f"  Transcript segs  : {len(segments)}")
print(f"  Matches found    : {len(matches)}")
print(f"  Clips produced   : {len(produced)}")
print(f"  Output directory : {OUTPUT_DIR}")
print()
