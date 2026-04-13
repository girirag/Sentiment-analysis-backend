import logging

import ffmpeg

logger = logging.getLogger(__name__)


class ClipExtractionError(Exception):
    """Raised when FFmpeg fails to extract a video clip."""


class ClipExtractor:
    def extract(
        self,
        video_path: str,
        start: float,
        end: float,
        output_path: str,
        video_duration: float,
    ) -> None:
        """Runs FFmpeg to cut [start-0.5, end+0.5] clamped to [0, video_duration]."""
        actual_start = max(0.0, start - 0.5)
        actual_end = min(video_duration, end + 0.5)

        try:
            (
                ffmpeg
                .input(video_path, ss=actual_start, to=actual_end)
                .output(output_path, vcodec="libx264", acodec="aac")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            logger.error("FFmpeg failed extracting clip from %s: %s", video_path, stderr)
            raise ClipExtractionError(
                f"FFmpeg failed to extract clip [{actual_start}, {actual_end}] "
                f"from {video_path}: {stderr}"
            ) from e
