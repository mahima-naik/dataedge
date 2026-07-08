"""Video compression utility for WhatsApp media sending.

Compresses videos larger than WhatsApp Web's upload limit using ffmpeg.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger


# WhatsApp Web upload limit for videos is roughly 16 MB. We target 14 MB to leave margin.
DEFAULT_MAX_SIZE_MB = 16
TARGET_SIZE_MB = 14


def _find_ffmpeg() -> Optional[str]:
    """Locate the ffmpeg binary on PATH."""
    ffmpeg = shutil.which("ffmpeg")
    return ffmpeg


def _get_file_size_mb(path: str) -> float:
    """Return file size in megabytes."""
    return os.path.getsize(path) / (1024 * 1024)


def _run_ffmpeg(input_path: str, output_path: str, crf: int, max_rate: str, scale: str = "") -> bool:
    """Run ffmpeg with given compression settings."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        logger.error("ffmpeg not found on PATH")
        return False

    cmd = [
        ffmpeg,
        "-y",
        "-threads", "0",
        "-i", input_path,
        "-vcodec", "libx264",
        "-crf", str(crf),
        "-preset", "veryfast",
        "-maxrate", max_rate,
        "-bufsize", max_rate,
        "-acodec", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-tune", "fastdecode",
    ]
    if scale:
        cmd.extend(["-vf", scale])
    cmd.extend([output_path])

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="ignore")[:500]
            logger.error("ffmpeg compression failed: {}", err)
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg compression timed out")
        return False
    except Exception as e:
        logger.error("ffmpeg compression error: {}", e)
        return False


def compress_video_if_needed(
    input_path: str,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
    target_size_mb: int = TARGET_SIZE_MB,
) -> str:
    """Return a path to a video under max_size_mb.

    If the video is already under the limit, the original path is returned.
    Otherwise ffmpeg is used to compress it in a temp directory. The caller
    is responsible for cleaning up the compressed temp file if desired.

    Args:
        input_path: Path to the original video.
        max_size_mb: Maximum allowed size in MB.
        target_size_mb: Target size in MB when compression is needed.

    Returns:
        Path to a video file under max_size_mb, or the original path if
        compression is unavailable or fails.
    """
    if not os.path.exists(input_path):
        logger.warning("Video not found: {}", input_path)
        return input_path

    size_mb = _get_file_size_mb(input_path)
    if size_mb <= max_size_mb:
        logger.debug("Video size {:.2f} MB is within limit, no compression needed", size_mb)
        return input_path

    if not _find_ffmpeg():
        logger.warning("ffmpeg not found, cannot compress video. Returning original.")
        return input_path

    logger.info(
        "Video size {:.2f} MB exceeds {} MB limit, compressing to target {} MB",
        size_mb, max_size_mb, target_size_mb,
    )

    # Suffix for compressed file
    suffix = Path(input_path).suffix or ".mp4"
    fd, output_path = tempfile.mkstemp(suffix=f"_compressed{suffix}", prefix="wa_video_")
    os.close(fd)

    # Progressive compression: try lower quality / resolution if still too big.
    attempts = [
        # (crf, max_rate, scale)
        (26, f"{target_size_mb}M", ""),
        (28, f"{target_size_mb}M", ""),
        (30, f"{target_size_mb}M", "scale='min(1280,iw)':-2"),
        (32, f"{target_size_mb}M", "scale='min(854,iw)':-2"),
        (34, f"{target_size_mb}M", "scale='min(640,iw)':-2"),
    ]

    for crf, max_rate, scale in attempts:
        if os.path.exists(output_path):
            os.remove(output_path)
        logger.debug("Compression attempt: crf={} max_rate={} scale={}", crf, max_rate, scale or "none")
        if _run_ffmpeg(input_path, output_path, crf, max_rate, scale):
            new_size_mb = _get_file_size_mb(output_path)
            logger.info("Compressed video to {:.2f} MB", new_size_mb)
            if new_size_mb <= max_size_mb:
                return output_path
            logger.warning("Still too large ({:.2f} MB), trying stronger compression", new_size_mb)

    # All attempts failed to get under limit; return original.
    logger.warning("Could not compress video under {} MB, returning original", max_size_mb)
    if os.path.exists(output_path):
        os.remove(output_path)
    return input_path
