"""Optional per-call 16 kHz mono WAV (inbound + outbound + mixed) for Vobiz WebSocket calls.

FIX: Sequential interleaved recording — inbound (user) and outbound (AI) chunks are
tagged with wall-clock timestamps and interleaved during close() so the mixed WAV
plays the conversation in chronological order (user question → AI answer → user question).
"""

from __future__ import annotations

import audioop
import struct
import threading
import wave
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from config import settings


import time

_SR = 16000
_BPS = 2  # bytes per sample (s16le)


def _safe_stem(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)[:180]


def _day_dir(base_dir: Optional[str] = None) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = Path(base_dir or settings.call_recording_dir).resolve()
    return base / day


class CallRecorder:
    """Appends 16 kHz s16le mono PCM to timestamped in-memory buffers;
    writes WAV/MP3 on close with sequential interleaved mixing.

    Each ``add_inbound`` / ``add_outbound`` call records the PCM along with
    ``time.time()``. During ``close()``, chunks are interleaved by timestamp
    so the mixed WAV plays the conversation in natural order.
    """

    def __init__(self, session_id: str, *, channel: str, base_dir: Optional[str] = None) -> None:
        self._session_id = session_id
        self._channel = channel
        self._lock = threading.Lock()
        self._in_path: Optional[str] = None
        self._out_path: Optional[str] = None
        # Timestamped chunks: list of (timestamp, pcm_bytes, direction)
        self._chunks: list[tuple[float, bytes, str]] = []
        self._start_time: float = time.time()
        self._in_written = 0
        self._out_written = 0
        self._in_first_write_t: Optional[float] = None
        self._out_first_write_t: Optional[float] = None
        # Reference time: set to Vobiz stream start for accurate alignment
        self._stream_start_t: Optional[float] = None

        if not settings.call_recording_enabled:
            return
        d = _day_dir(base_dir)
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Call recording: cannot create dir {}: {}", d, e)
            return
        stem = _safe_stem(session_id)
        self._in_path = str(d / f"{stem}_inbound.wav")
        self._out_path = str(d / f"{stem}_outbound.wav")
        self._start_time = time.time()
        
        logger.info(
            "Call recording: initialized memory buffers for channel={} session={} in={} out={}",
            channel,
            session_id,
            self._in_path,
            self._out_path,
        )

    def set_stream_start(self, t: Optional[float] = None) -> None:
        """Set the Vobiz stream start reference time for accurate alignment."""
        self._stream_start_t = t if t is not None else time.perf_counter()

    def add_inbound(self, pcm_s16le_mono: bytes) -> None:
        """Append inbound PCM with timestamp. Lock-free for CPython."""
        if not self._in_path or not pcm_s16le_mono:
            return
        now = time.perf_counter()
        if self._in_first_write_t is None:
            self._in_first_write_t = now
        # Store as (timestamp, pcm, direction)
        self._chunks.append((now, pcm_s16le_mono, "in"))
        self._in_written += len(pcm_s16le_mono)

    def add_outbound(self, pcm_s16le_mono: bytes) -> None:
        """Append outbound PCM with timestamp. Lock-free for CPython."""
        if not self._out_path or not pcm_s16le_mono:
            return
        now = time.perf_counter()
        if self._out_first_write_t is None:
            self._out_first_write_t = now
        # Store as (timestamp, pcm, direction)
        self._chunks.append((now, pcm_s16le_mono, "out"))
        self._out_written += len(pcm_s16le_mono)

    def close(self) -> None:
        if self._in_path or self._out_path:
            logger.info(
                "Call recording: closed channel={} session={} (flushing {} chunks to background thread)",
                self._channel,
                self._session_id,
                len(self._chunks),
            )
            threading.Thread(target=self._write_recording_wav, daemon=True).start()

    @staticmethod
    def _pcm_energy(pcm: bytes) -> float:
        """Compute RMS energy of PCM s16le mono (used for silence detection)."""
        if len(pcm) < 2:
            return 0.0
        n = len(pcm) // 2
        total = 0
        for i in range(n):
            s = struct.unpack_from("<h", pcm, i * 2)[0]
            total += s * s
        return (total / n) ** 0.5

    def _write_recording_wav(self) -> None:
        """Write inbound, outbound, and sequentially-interleaved mixed WAV/MP3.

        The mixed WAV is built by sorting all chunks by timestamp and writing
        them in chronological order. When both inbound and outbound chunks
        overlap at the same time, the outbound (AI) chunk is placed AFTER the
        inbound (user) chunk by adjusting its effective timestamp to be
        slightly later (offset by the chunk duration). This prevents AI audio
        from being heard before the user's question.
        """
        if not self._chunks:
            return

        with self._lock:
            chunks = list(self._chunks)
            self._chunks.clear()

        # Separate inbound and outbound chunks
        in_chunks: list[tuple[float, bytes]] = []
        out_chunks: list[tuple[float, bytes]] = []
        for ts, pcm, direction in chunks:
            if direction == "in":
                in_chunks.append((ts, pcm))
            else:
                out_chunks.append((ts, pcm))

        # Write inbound WAV
        if self._in_path and in_chunks:
            self._write_wav_from_chunks(self._in_path, in_chunks, "inbound")

        # Write outbound WAV
        if self._out_path and out_chunks:
            self._write_wav_from_chunks(self._out_path, out_chunks, "outbound")

        # Write sequentially-interleaved mixed WAV
        mixed_path = None
        try:
            if not in_chunks and not out_chunks:
                return

            # Build interleaved timeline
            mixed_frames = self._build_sequential_mixed(in_chunks, out_chunks)
            if not mixed_frames:
                return

            stem = Path(self._in_path or self._out_path).stem
            for suffix in ("_inbound", "_outbound"):
                if stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            
            mixed_path = str(Path((self._in_path or self._out_path)).parent / f"{stem}_mixed.wav")
            with wave.open(mixed_path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(_SR)
                w.writeframes(mixed_frames)
            logger.info("Call recording: sequential mixed WAV written {} ({} B, {:.1f}s)",
                        mixed_path, len(mixed_frames), len(mixed_frames) / (_SR * _BPS))

            # Compress to MP3
            mp3_path = mixed_path.replace(".wav", ".mp3")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", mixed_path, "-acodec", "libmp3lame", "-b:a", "64k", mp3_path],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info("Call recording: compressed to MP3 {}", mp3_path)
                Path(mixed_path).unlink(missing_ok=True)
            except Exception as ffmpeg_err:
                logger.warning("Call recording: MP3 compression failed: {}", ffmpeg_err)
        except Exception as e:
            logger.exception("Call recording mix failed: {}", e)

    def _build_sequential_mixed(
        self,
        in_chunks: list[tuple[float, bytes]],
        out_chunks: list[tuple[float, bytes]],
    ) -> bytes:
        """Build a sequential mixed recording from timestamped chunks.

        Algorithm:
        1. All chunks are tagged with (timestamp, pcm, direction).
        2. Sort by timestamp.
        3. For overlapping chunks (AI starting while user still speaking):
           - The user (inbound) audio takes priority at that timestamp.
           - The AI (outbound) audio is delayed to start AFTER the user chunk ends.
        4. Fill gaps with silence.
        5. Result: user question always precedes AI answer.
        """
        if not in_chunks and not out_chunks:
            return b""

        ref_t = self._stream_start_t or (
            min(
                (c[0] for c in in_chunks),
                default=(out_chunks[0][0] if out_chunks else time.time()),
            )
            if in_chunks or out_chunks
            else time.time()
        )

        # Convert to (relative_time_sec, pcm, direction) tuples
        tagged: list[tuple[float, bytes, str]] = []
        for ts, pcm in in_chunks:
            tagged.append(((ts - ref_t), pcm, "in"))
        for ts, pcm in out_chunks:
            tagged.append(((ts - ref_t), pcm, "out"))

        # Sort by timestamp
        tagged.sort(key=lambda x: x[0])

        # Build sequential output: ensure outbound never precedes inbound at same time
        # When overlap detected, delay outbound chunk to end of inbound chunk
        result = bytearray()
        last_end_time = 0.0  # tracks the end time of the last written audio

        for t_start, pcm, direction in tagged:
            duration = len(pcm) / (_SR * _BPS)
            t_end = t_start + duration

            if direction == "in":
                # Inbound (user) always writes at its natural position
                silence_needed = max(0, t_start - last_end_time)
                if silence_needed > 0.005:  # >5ms gap
                    result.extend(b"\x00" * int(silence_needed * _SR * _BPS))
                result.extend(pcm)
                last_end_time = max(last_end_time, t_end)
            else:
                # Outbound (AI) — must not start before last user audio ends
                effective_start = max(t_start, last_end_time)
                silence_needed = max(0, effective_start - last_end_time)
                if silence_needed > 0.005:
                    result.extend(b"\x00" * int(silence_needed * _SR * _BPS))
                result.extend(pcm)
                last_end_time = max(last_end_time, effective_start + duration)

        return bytes(result)

    def _write_wav_from_chunks(
        self, path: str, chunks: list[tuple[float, bytes]], label: str
    ) -> None:
        """Write a single-direction WAV from timestamped chunks (with gap-filling silence)."""
        if not chunks:
            return
        try:
            ref_t = self._stream_start_t or chunks[0][0]
            pcm_parts = bytearray()
            last_end = 0.0
            for ts, pcm in chunks:
                t_start = ts - ref_t
                duration = len(pcm) / (_SR * _BPS)
                gap = max(0, t_start - last_end)
                if gap > 0.005:
                    pcm_parts.extend(b"\x00" * int(gap * _SR * _BPS))
                pcm_parts.extend(pcm)
                last_end = t_start + duration
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(_SR)
                w.writeframes(bytes(pcm_parts))
        except Exception as e:
            logger.exception("Call recording: failed to write {} WAV {}: {}", label, path, e)

    def meta(self) -> dict[str, Any]:
        return {
            "inbound_wav": self._in_path,
            "outbound_wav": self._out_path,
            "call_recording": bool(self._in_path or self._out_path),
            "total_chunks": len(self._chunks),
        }


def _parse_log_id_date(session_id: str) -> str | None:
    """Extract YYYY-MM-DD from log_id patterns like camp-xxx-20260513T07291 or vobiz-live-20260518T161022-xxx."""
    import re
    m = re.search(r"(\d{4})(\d{2})(\d{2})T", session_id)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _search_recording_dirs(
    stem: str,
    roots: list[Path],
    date_hint: str | None = None,
    scan_recent_days: int = 31,
) -> Path | None:
    """Search multiple recording roots for a matching WAV file."""
    suffixes = ("_mixed", "_outbound", "_inbound")
    for root in roots:
        if not root.is_dir():
            continue
        for sfx in suffixes:
            for ext in (".mp3", ".wav"):
                cand = root / f"{stem}{sfx}{ext}"
                if cand.is_file():
                    return cand
        if date_hint:
            day_dir = root / date_hint
            if day_dir.is_dir():
                for sfx in suffixes:
                    for ext in (".mp3", ".wav"):
                        cand = day_dir / f"{stem}{sfx}{ext}"
                        if cand.is_file():
                            return cand
        dirs = sorted(
            (p for p in root.iterdir() if p.is_dir() and len(p.name) == 10),
            key=lambda p: p.name,
            reverse=True,
        )
        for day in dirs[: max(7, scan_recent_days)]:
            for sfx in suffixes:
                for ext in (".mp3", ".wav"):
                    cand = day / f"{stem}{sfx}{ext}"
                    if cand.is_file():
                        return cand
    return None


def recording_search_roots(base_dir: Optional[str | Path] = None) -> list[Path]:
    """All WAV directories to search (live DataEdge + historical agent/vernika trees)."""

    import os

    roots: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except OSError:
            return
        if key in seen:
            return
        if p.is_dir():
            seen.add(key)
            roots.append(p)

    if base_dir:
        _add(Path(base_dir))
    else:
        _add(Path(settings.call_recording_dir))
        for extra in (os.getenv("CALL_RECORDING_EXTRA_DIRS") or "").split(","):
            extra = extra.strip()
            if extra:
                _add(Path(extra))
        for candidate in (
            "/root/vernika/backend/data/call_recordings",
            "/root/vernika/agent/data/call_recordings",
            "/root/DataEdge/backend/data/call_recordings",
        ):
            _add(Path(candidate))
        _recordings_dir = Path(__file__).resolve().parent.parent / "data" / "recordings"
        _add(_recordings_dir)
    return roots


def resolve_session_recording_path(
    session_id: str,
    base_dir: Optional[str | Path] = None,
    *,
    scan_recent_days: int = 60,
) -> Path | None:
    """Locate ``*_mixed.wav`` (preferred) or outbound/inbound WAV for a CallRecorder ``session_id``."""

    stem = _safe_stem(session_id.strip())
    if not stem:
        return None

    date_hint = _parse_log_id_date(session_id)
    return _search_recording_dirs(
        stem, recording_search_roots(base_dir), date_hint, scan_recent_days
    )


def list_recording_days(base_dir: Optional[str] = None) -> list[str]:
    base = Path(base_dir or settings.call_recording_dir).resolve()
    if not base.is_dir():
        return []
    return sorted(
        [p.name for p in base.iterdir() if p.is_dir() and len(p.name) == 10],
        reverse=True,
    )


def list_recordings_wavs(day: str, base_dir: Optional[str] = None) -> list[str]:
    d = Path(base_dir or settings.call_recording_dir).resolve() / day
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.glob("*.wav"))


def resolve_recording_file(day: str, filename: str, base_dir: Optional[str] = None) -> Optional[Path]:
    if not day or len(day) != 10 or ".." in day or "/" in day or "\\" in day:
        return None
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return None
    safe = Path(filename).name
    if safe != filename or not (safe.lower().endswith(".wav") or safe.lower().endswith(".mp3")):
        return None
    
    base_root = Path(base_dir or settings.call_recording_dir).resolve()
    p = (base_root / day / safe).resolve()
    if not p.is_file():
        stem = safe.rsplit(".", 1)[0]
        mixed_mp3 = (base_root / day / f"{stem}_mixed.mp3").resolve()
        if mixed_mp3.is_file():
            p = mixed_mp3
        else:
            mixed_wav = (base_root / day / f"{stem}_mixed.wav").resolve()
            if mixed_wav.is_file():
                p = mixed_wav
            
    root = (base_root / day).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p if p.is_file() else None
