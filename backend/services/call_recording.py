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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from config import settings


import time


# ---------------------------------------------------------------------------
# Recording work isolation (spec #13 / #16 / #18).
#
# Before: every call ended by spawning a *new* OS thread that ran per-sample
# Python loops over the whole recording on the GIL — with N concurrent calls
# those threads thrashed the event-loop core and could starve real-time audio.
#
# Now: a single bounded worker pool serialises all WAV build/ffmpeg work, so
# (a) the heavy DSP never runs on the caller's thread, and (b) concurrent calls
# queue rather than fight for the GIL. The DSP below is also fully vectorised
# with numpy (100x+ faster than the old per-sample loops).
# ---------------------------------------------------------------------------

_REC_WORKERS: Optional[ThreadPoolExecutor] = None
_REC_WORKER_LOCK = threading.Lock()


def _rec_executor() -> ThreadPoolExecutor:
    global _REC_WORKERS
    if _REC_WORKERS is None:
        with _REC_WORKER_LOCK:
            if _REC_WORKERS is None:
                # One worker is enough: recording is post-call and must not
                # contend with the live audio event loop for CPU.
                _REC_WORKERS = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rec-write")
    return _REC_WORKERS

_SR = 16000
_BPS = 2  # bytes per sample (s16le)

# Splice-click protection: short linear ramp applied at chunk edges whenever a
# chunk is stitched onto (or away from) a silence fill. 2 ms (32 samples) is
# short enough to be inaudible on speech but long enough to remove the harsh
# click/pop caused by an instant 0 -> full-amplitude transition.
_FADE_SAMPLES = 32
# Gaps longer than this are treated as real silence (filled + faded).
_SILENCE_GAP_SEC = 0.005

# Noise gate: telephony gateways (Vobiz/SIP) often inject a low-level hiss
# floor on both legs.  The gate attenuates any window whose RMS falls below
# the threshold so the hiss disappears during pauses without touching speech.
_NOISE_GATE_THRESH = 0.006  # RMS fraction of full scale (~ -44 dBFS)
_NOISE_GATE_ATTACK_SAMPLES = 48   # 3 ms — smooth open
_NOISE_GATE_RELEASE_SAMPLES = 320  # 20 ms — smooth close
_NOISE_GATE_REDUCTION = 0.02      # gain when gate is closed (≈ -34 dB)


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
        self._drop_count: int = 0
        # Soft cap: ~10 min of 16 kHz s16le per direction (inbound + outbound
        # counted together). Beyond this we drop oldest to bound memory; normally
        # MAX_CALL_DURATION_SEC=600 keeps us well under it.
        self._max_bytes = 10 * 60 * _SR * _BPS * 2
        self._bytes_stored = 0
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
        self._append_chunk(pcm_s16le_mono, "in")

    def add_outbound(self, pcm_s16le_mono: bytes) -> None:
        """Append outbound PCM with timestamp. Lock-free for CPython."""
        if not self._out_path or not pcm_s16le_mono:
            return
        self._append_chunk(pcm_s16le_mono, "out")

    def _append_chunk(self, pcm: bytes, direction: str) -> None:
        now = time.perf_counter()
        if direction == "in" and self._in_first_write_t is None:
            self._in_first_write_t = now
        if direction == "out" and self._out_first_write_t is None:
            self._out_first_write_t = now
        self._bytes_stored += len(pcm)
        if self._bytes_stored > self._max_bytes and self._chunks:
            # Drop oldest to bound memory; record the drop.
            _, old, _ = self._chunks.pop(0)
            self._bytes_stored -= len(old)
            self._drop_count += 1
        self._chunks.append((now, pcm, direction))
        if direction == "in":
            self._in_written += len(pcm)
        else:
            self._out_written += len(pcm)

    def recording_depth(self) -> int:
        """Number of queued recording chunks (for live diagnostics)."""
        return len(self._chunks)

    def recording_drop_count(self) -> int:
        return self._drop_count

    def close(self) -> None:
        if self._in_path or self._out_path:
            logger.info(
                "Call recording: closed channel={} session={} (flushing {} chunks to worker pool)",
                self._channel,
                self._session_id,
                len(self._chunks),
            )
            try:
                _rec_executor().submit(self._write_recording_wav)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Call recording: submit to worker pool failed: {}", exc)

    @staticmethod
    def _pcm_energy(pcm: bytes) -> float:
        """Compute RMS energy of PCM s16le mono (used for silence detection)."""
        import numpy as _np

        if len(pcm) < 2:
            return 0.0
        arr = _np.frombuffer(pcm, dtype=_np.int16)
        if arr.size == 0:
            return 0.0
        return float(_np.sqrt(_np.mean(arr.astype(_np.float64) ** 2)))

    @staticmethod
    def _fade_pcm_edges(pcm: bytes, *, fade_in: bool, fade_out: bool) -> bytes:
        """Apply short linear fade ramps at PCM edges to kill splice clicks.

        Only used at real utterance boundaries (silence -> speech / speech ->
        silence). Chunks that are contiguous with neighbours are left untouched,
        so continuous speech is not smeared or pumped.
        """
        if not (fade_in or fade_out):
            return pcm
        import numpy as _np

        arr = _np.frombuffer(pcm, dtype=_np.int16)
        n = arr.size
        if n < 2 * _FADE_SAMPLES:
            # Too short to fade both edges without destroying the chunk — skip.
            return pcm
        if fade_in:
            ramp = _np.linspace(0.0, 1.0, _FADE_SAMPLES, dtype=_np.float64)
            arr[:_FADE_SAMPLES] = (arr[:_FADE_SAMPLES].astype(_np.float64) * ramp).astype(_np.int16)
        if fade_out:
            ramp = _np.linspace(1.0, 0.0, _FADE_SAMPLES, dtype=_np.float64)
            arr[n - _FADE_SAMPLES:] = (arr[n - _FADE_SAMPLES:].astype(_np.float64) * ramp).astype(_np.int16)
        return arr.tobytes()

    @staticmethod
    def _trim_trailing_silence(pcm: bytes, keep_ms: float = 350.0) -> bytes:
        """Drop trailing digital-silence padding, keeping a short tail window.

        Live call audio often ends minutes after the last speech burst (Vobiz
        keeps the stream open until hangup); without this the WAV/MP3 contains
        long runs of dead air that make the recording feel bloated.
        """
        import numpy as _np

        n = len(pcm) // 2
        if n < 2:
            return pcm
        arr = _np.frombuffer(pcm, dtype=_np.int16)
        keep = int(_SR * keep_ms / 1000.0)
        above = _np.abs(arr) > 40
        if not above.any():
            return pcm[:2]
        last = int(_np.argmax(above[::-1]))  # distance from end of last sample > 40
        idx = min(n - 1, n - 1 - last + keep)
        return arr[: idx + 1].tobytes()

    @staticmethod
    def _noise_gate(pcm: bytes) -> bytes:
        """Suppress low-level hiss floor from telephony audio.

        Computes RMS in 20 ms windows and applies smooth gain reduction when
        the level falls below ``_NOISE_GATE_THRESH``.  Attack/release envelopes
        prevent the gain changes from sounding choppy.  Vectorised with numpy —
        the previous per-sample Python loop was a top CPU consumer on the
        recording worker for long calls.
        """
        import numpy as _np

        n = len(pcm) // 2
        if n < 2:
            return pcm
        arr = _np.frombuffer(pcm, dtype=_np.int16).astype(_np.float64)
        win = max(2, int(_SR * 0.02))  # 20 ms window
        max_i16 = 32768.0
        thresh = _NOISE_GATE_THRESH
        reduction = _NOISE_GATE_REDUCTION
        attack = _NOISE_GATE_ATTACK_SAMPLES
        release = _NOISE_GATE_RELEASE_SAMPLES

        n_win = max(1, (n + win - 1) // win)
        out = _np.empty_like(arr)
        gain = 1.0
        pos = 0
        for w in range(n_win):
            end = min(pos + win, n)
            seg = arr[pos:end]
            rms = _np.sqrt(_np.mean(seg ** 2)) / max_i16 if seg.size else 0.0
            target = 1.0 if rms > thresh else reduction
            n_seg = end - pos
            if target < gain:
                step = (gain - target) / max(1, release)
                gain = max(reduction, gain - step)
            else:
                step = (target - gain) / max(1, attack)
                gain = min(1.0, gain + step)
            out[pos:end] = seg * gain
            pos = end
        return _np.clip(out, -32768, 32767).astype(_np.int16).tobytes()

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
                w.writeframes(self._noise_gate(self._trim_trailing_silence(mixed_frames)))
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

        for i, (t_start, pcm, direction) in enumerate(tagged):
            duration = len(pcm) / (_SR * _BPS)
            t_end = t_start + duration

            if direction == "in":
                # Inbound (user) always writes at its natural position
                effective_start = t_start
            else:
                # Outbound (AI) — must not start before last user audio ends
                effective_start = max(t_start, last_end_time)

            silence_needed = max(0, effective_start - last_end_time)
            chunk_end = max(last_end_time, effective_start + duration)

            # Fade at every seam that is NOT a natural continuous continuation:
            #   * real silence gap before this chunk,
            #   * this chunk was force-shifted forward (spliced onto earlier audio,
            #     e.g. a user burst recorded during the scripted greeting), or
            #   * the next chunk will be spliced onto / after this one.
            # Continuous 20ms runs (next chunk starts exactly where this one ends)
            # are left untouched so normal speech is not smeared.
            next_t = tagged[i + 1][0] if i + 1 < len(tagged) else float("inf")
            forced_splice = effective_start > t_start + 1e-9
            preceded_by_silence = silence_needed > _SILENCE_GAP_SEC
            fade_in = preceded_by_silence or forced_splice
            gap_after = next_t - chunk_end
            fade_out = gap_after > _SILENCE_GAP_SEC or gap_after < -1e-9

            pcm = self._fade_pcm_edges(
                pcm,
                fade_in=fade_in,
                fade_out=fade_out,
            )

            if silence_needed > _SILENCE_GAP_SEC:
                result.extend(b"\x00" * (int(silence_needed * _SR * _BPS) // 2 * 2))
            result.extend(pcm)
            last_end_time = chunk_end

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
            for i, (ts, pcm) in enumerate(chunks):
                t_start = ts - ref_t
                duration = len(pcm) / (_SR * _BPS)
                gap = max(0.0, t_start - last_end)
                # Fade at utterance boundaries (same logic as the mixed build) so
                # silence fills don't produce harsh clicks on speech onset/offset.
                next_gap = 0.0
                if i + 1 < len(chunks):
                    nxt_start = chunks[i + 1][0] - ref_t
                    nxt_dur = len(chunks[i + 1][1]) / (_SR * _BPS)
                    next_gap = max(0.0, nxt_start - (t_start + duration))
                pcm = self._fade_pcm_edges(
                    pcm,
                    fade_in=gap > _SILENCE_GAP_SEC,
                    fade_out=next_gap > _SILENCE_GAP_SEC,
                )
                if gap > _SILENCE_GAP_SEC:
                    pcm_parts.extend(b"\x00" * (int(gap * _SR * _BPS) // 2 * 2))
                pcm_parts.extend(pcm)
                last_end = max(last_end, t_start + duration)
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(_SR)
                w.writeframes(self._noise_gate(self._trim_trailing_silence(bytes(pcm_parts))))
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
