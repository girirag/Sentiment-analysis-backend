"""Clip highlights API routes — mounted at /api/videos/{video_id}/clips"""
import base64
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path as PathParam, UploadFile, status

from app.api.dependencies import verify_auth_token
from app.config import settings
from app.models.schemas import (
    ClipDownloadResponse,
    ClipGenerateResponse,
    ClipJobStatus,
    ClipResult,
)
from app.services.firebase_service import firebase_service

logger = logging.getLogger(__name__)

router = APIRouter(redirect_slashes=False)

# ── Dev-mode file-backed stores (survives server restarts) ───────────────────
import pathlib as _pl
_STORE_DIR = _pl.Path(__file__).parent.parent.parent.parent / "uploads" / "_dev_store"
_STORE_DIR.mkdir(exist_ok=True)
_JOBS_FILE  = _STORE_DIR / "jobs.json"
_CLIPS_FILE = _STORE_DIR / "clips.json"

def _load(path: _pl.Path) -> dict:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}

def _save(path: _pl.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))

def _dev_save_job(job: Dict) -> None:
    store = _load(_JOBS_FILE)
    store[job["job_id"]] = job
    _save(_JOBS_FILE, store)

def _dev_get_job(job_id: str) -> Dict | None:
    return _load(_JOBS_FILE).get(job_id)

def _dev_update_job(job_id: str, updates: dict) -> None:
    store = _load(_JOBS_FILE)
    if job_id in store:
        store[job_id].update(updates)
        _save(_JOBS_FILE, store)

def _dev_save_clip(clip: Dict) -> None:
    store = _load(_CLIPS_FILE)
    store[clip["clip_id"]] = clip
    _save(_CLIPS_FILE, store)

def _dev_get_clips_for_video(video_id: str, job_id: str = None) -> List[Dict]:
    all_clips = list(_load(_CLIPS_FILE).values())
    # If job_id provided, only return clips from that job
    if job_id:
        clips = [c for c in all_clips if c["video_id"] == video_id and c["job_id"] == job_id]
    else:
        clips = [c for c in all_clips if c["video_id"] == video_id]
    return sorted(clips, key=lambda c: c["start_time"])

def _dev_get_clip(clip_id: str) -> Dict | None:
    return _load(_CLIPS_FILE).get(clip_id)

# Import Celery task with graceful fallback
try:
    from app.tasks.celery_tasks import generate_clips_task

    CELERY_AVAILABLE = True
    logger.info("generate_clips_task imported successfully")
except Exception as _e:
    CELERY_AVAILABLE = False
    logger.warning(f"generate_clips_task not available: {_e}")

# Dataset upload constraints
MAX_DATASET_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".json", ".csv", ".txt"}


def _get_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


async def _get_owned_video(video_id: str, user_id: str) -> Dict[str, Any]:
    """
    Fetch the video document and enforce ownership.
    In development mode, reads from local videos.json.
    """
    # Dev mode: read from local JSON
    if settings.environment == "development" or settings.debug:
        import json, os
        videos_file = os.path.join(os.getcwd(), "uploads", "videos.json")
        if os.path.exists(videos_file):
            with open(videos_file) as f:
                videos = json.load(f)
            video = next((v for v in videos if v.get("video_id") == video_id), None)
            if not video:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
            owner = video.get("userId") or video.get("user_id")
            if owner != user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this video")
            return video

    video = await firebase_service.get_video(video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )
    owner = video.get("userId") or video.get("user_id")
    if owner != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this video",
        )
    return video


# ---------------------------------------------------------------------------
# Dev-mode pipeline (runs as FastAPI BackgroundTask, no Celery/Firebase)
# ---------------------------------------------------------------------------

def _run_pipeline_dev(
    job_id: str, video_id: str, dataset_bytes: bytes,
    dataset_filename: str, similarity_threshold: float,
) -> None:
    import glob, shutil, tempfile
    from pathlib import Path

    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_TORCH", "1")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

    from app.services.clip_extractor import ClipExtractor, ClipExtractionError
    from app.services.dataset_parser import DatasetParser
    from app.services.semantic_matcher import SemanticMatcher
    from pathlib import Path as FilePath

    backend_dir = FilePath(__file__).parent.parent.parent.parent
    uploads_dir = backend_dir / "uploads"
    clips_dir = uploads_dir / "test_clips"
    clips_dir.mkdir(exist_ok=True)

    def _update(updates: dict) -> None:
        _dev_update_job(job_id, updates)

    try:
        _update({"status": "processing"})

        # Locate video
        candidates = [
            f for f in glob.glob(str(uploads_dir / f"{video_id}_*"))
            if f.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))
        ]
        if not candidates:
            raise FileNotFoundError(f"Video file not found for {video_id}")
        video_path = candidates[0]

        # Load transcript
        analysis_path = uploads_dir / f"{video_id}_analysis.json"
        if not analysis_path.exists():
            raise FileNotFoundError(f"Analysis JSON not found: {analysis_path}")
        with open(analysis_path, encoding="utf-8") as f:
            analysis = json.load(f)

        raw_segs = analysis.get("timeline", [])
        segments = []
        for i, seg in enumerate(raw_segs):
            start = float(seg.get("timestamp", 0.0))
            end = float(raw_segs[i + 1]["timestamp"]) if i + 1 < len(raw_segs) else start + 10.0
            segments.append({
                "text": seg.get("text", ""), "start": start, "end": end,
                "original_language": seg.get("original_language", ""),
                "translated_text": seg.get("translated_text", ""),
            })
        video_duration = segments[-1]["end"] if segments else 0.0

        # Parse + match
        entries = DatasetParser().parse(dataset_bytes, dataset_filename)
        matches = SemanticMatcher().match(entries, segments, threshold=similarity_threshold)

        # ── Keep only the top matches by score, then merge adjacent segments ──
        MAX_CLIPS = 10
        MIN_GAP_SECONDS = 5.0  # merge segments closer than this

        # Sort by score descending, take top N
        matches = sorted(matches, key=lambda m: m.similarity_score, reverse=True)[:MAX_CLIPS]
        # Re-sort by time for merging
        matches = sorted(matches, key=lambda m: m.segment["start"])

        # Merge adjacent/overlapping segments into single clips
        merged = []
        for m in matches:
            seg = m.segment
            if merged and seg["start"] - merged[-1]["end"] < MIN_GAP_SECONDS:
                # Extend the last merged clip
                merged[-1]["end"] = max(merged[-1]["end"], seg["end"])
                if m.similarity_score > merged[-1]["score"]:
                    merged[-1]["score"] = m.similarity_score
                    merged[-1]["text"] = seg.get("text", "")
                    merged[-1]["dataset_entry"] = m.dataset_entry
            else:
                merged.append({
                    "start": seg["start"], "end": seg["end"],
                    "text": seg.get("text", ""),
                    "dataset_entry": m.dataset_entry,
                    "score": m.similarity_score,
                })

        logger.info("Matches: %d → after top-%d + merge: %d clips", len(matches), MAX_CLIPS, len(merged))

        # Extract clips
        extractor = ClipExtractor()
        clip_ids = []
        for m in merged:
            clip_id = str(uuid.uuid4())
            out_path = str(clips_dir / f"{clip_id}.mp4")
            try:
                extractor.extract(video_path, m["start"], m["end"], out_path, video_duration)
            except ClipExtractionError as e:
                logger.error("Skipping clip: %s", e)
                continue
            clip = {
                "clip_id": clip_id, "video_id": video_id, "job_id": job_id,
                "start_time": m["start"], "end_time": m["end"],
                "matched_text": m["text"],
                "dataset_entry": m["dataset_entry"],
                "similarity_score": m["score"],
                "storage_path": f"clips/{video_id}/{clip_id}.mp4",
            }
            _dev_save_clip(clip)
            clip_ids.append(clip_id)

        _update({"status": "completed", "clip_ids": clip_ids})
        logger.info("Dev pipeline done: job=%s clips=%d", job_id, len(clip_ids))

    except Exception as e:
        logger.error("Dev pipeline failed: %s", e)
        _update({"status": "failed", "error": str(e)})


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=ClipGenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_clips(
    background_tasks: BackgroundTasks,
    video_id: str = PathParam(...),
    file: UploadFile = File(...),
    similarity_threshold: float = Form(0.5),
    user_info: Dict[str, Any] = Depends(verify_auth_token),
):
    """
    Accept a dataset file and enqueue a clip-generation task.
    In dev mode runs the pipeline as a background task without Celery/Firebase.
    """
    user_id: str = user_info["uid"]
    await _get_owned_video(video_id, user_id)

    ext = _get_extension(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_DATASET_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset file exceeds the 10 MB size limit",
        )

    job_id = str(uuid.uuid4())

    if settings.environment == "development" or settings.debug:
        # Clear old clips for this video so stale results don't accumulate
        old_clips = _load(_CLIPS_FILE)
        cleaned = {k: v for k, v in old_clips.items() if v.get("video_id") != video_id}
        _save(_CLIPS_FILE, cleaned)

        _dev_save_job({
            "job_id": job_id, "video_id": video_id, "user_id": user_id,
            "status": "queued", "similarity_threshold": similarity_threshold,
            "clip_ids": [], "error": None,
        })
        background_tasks.add_task(
            _run_pipeline_dev, job_id, video_id, content,
            file.filename or f"dataset{ext}", similarity_threshold,
        )
        return ClipGenerateResponse(job_id=job_id, status="queued")

    # Production: use Celery + Firebase
    await firebase_service.create_clip_job(
        job_id=job_id, video_id=video_id, user_id=user_id,
        similarity_threshold=similarity_threshold,
    )
    if not CELERY_AVAILABLE:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Background processing service is not available")
    generate_clips_task.delay(
        job_id=job_id, video_id=video_id, user_id=user_id,
        dataset_content=base64.b64encode(content).decode(),
        dataset_filename=file.filename or f"dataset{ext}",
        similarity_threshold=similarity_threshold,
    )
    return ClipGenerateResponse(job_id=job_id, status="queued")


# ---------------------------------------------------------------------------
# GET /status/{job_id}
# ---------------------------------------------------------------------------

@router.get("/status/{job_id}", response_model=ClipJobStatus)
async def get_clip_job_status(
    video_id: str = PathParam(...),
    job_id: str = PathParam(...),
    user_info: Dict[str, Any] = Depends(verify_auth_token),
):
    """Return the current status of a clip generation job."""
    user_id: str = user_info["uid"]
    await _get_owned_video(video_id, user_id)

    if settings.environment == "development" or settings.debug:
        job = _dev_get_job(job_id)
    else:
        job = await firebase_service.get_clip_job(job_id)

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip job not found")

    return ClipJobStatus(
        job_id=job["job_id"], video_id=job["video_id"], status=job["status"],
        clip_ids=job.get("clip_ids", []), error=job.get("error"),
    )


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[ClipResult])
@router.get("", response_model=List[ClipResult])
async def list_clip_results(
    video_id: str = PathParam(...),
    user_info: Dict[str, Any] = Depends(verify_auth_token),
):
    """Return all Clip_Results for a video, ordered by start_time ascending."""
    user_id: str = user_info["uid"]
    await _get_owned_video(video_id, user_id)

    if settings.environment == "development" or settings.debug:
        # Find the latest completed job for this video and return only its clips
        jobs = _load(_JOBS_FILE)
        latest_job = None
        for job in sorted(jobs.values(), key=lambda j: j.get("job_id", ""), reverse=True):
            if job.get("video_id") == video_id and job.get("status") == "completed":
                latest_job = job
                break
        job_id_filter = latest_job["job_id"] if latest_job else None
        results = _dev_get_clips_for_video(video_id, job_id=job_id_filter)
    else:
        results = await firebase_service.get_clip_results_for_video(video_id)

    return [
        ClipResult(
            clip_id=r["clip_id"], video_id=r["video_id"],
            start_time=r["start_time"], end_time=r["end_time"],
            matched_text=r["matched_text"], dataset_entry=r["dataset_entry"],
            similarity_score=r["similarity_score"], storage_path=r["storage_path"],
        )
        for r in results
    ]


# ---------------------------------------------------------------------------
# GET /{clip_id}/download
# ---------------------------------------------------------------------------

@router.get("/{clip_id}/download", response_model=ClipDownloadResponse)
async def download_clip(
    video_id: str = PathParam(...),
    clip_id: str = PathParam(...),
    user_info: Dict[str, Any] = Depends(verify_auth_token),
):
    """Return a download URL for a Highlight_Clip."""
    user_id: str = user_info["uid"]
    await _get_owned_video(video_id, user_id)

    if settings.environment == "development" or settings.debug:
        clip = _dev_get_clip(clip_id)
    else:
        clip = await firebase_service.get_clip_result(clip_id)

    if not clip or clip.get("video_id") != video_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    # Dev mode: serve the local file via the static mount
    if settings.environment == "development" or settings.debug:
        from pathlib import Path as FilePath
        filename = FilePath(clip["storage_path"]).name
        download_url = f"http://localhost:8000/static/analysis/test_clips/{filename}"
        return ClipDownloadResponse(clip_id=clip_id, download_url=download_url, expires_in=3600)

    expiration = 3600
    try:
        download_url = await firebase_service.get_file_url(clip["storage_path"], expiration=expiration)
    except Exception as e:
        logger.error(f"Failed to generate signed URL for clip {clip_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate download URL")

    return ClipDownloadResponse(clip_id=clip_id, download_url=download_url, expires_in=expiration)
