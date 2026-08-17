"""Optional per-call 16 kHz mono WAV (inbound + outbound + mixed) for Vobiz WebSocket calls.

Recording model
---------------

The recording is built from the **ordered audio stream**, not from packet
arrival times.  For every call we keep two independent, *continuous* timelines:

* inbound  — customer audio, in the order frames arrived (Vobiz delivers
  media in order even when the WebSocket lumps/bursts them).
* outbound — AI audio (scripted greeting, Gemini Live resampler output, and any
  TTS fallback), in the order it was produced.

Each frame is assigned a monotonic sequence number and a continuous sample
position (previous position + sample count).  Wall-clock arrival time is
recorded **only for diagnostics**; it is never used to decide whether silence
exists in the conversation.

A late frame is still valid audio: a 200 ms network delay does **not** become
200 ms of silence in the recording.  The only silence we ever reconstruct is a
single coarse lead-in used to align the two timelines (based on the first
frame of each direction), never per-chunk gaps.

**Mixed recording (gap-aware):**  The ``<stem>_mixed.wav/.mp3`` artifact uses
a different strategy from the per-direction WAVs.  It reconstructs silence
gaps from inter-chunk arrival timestamps so that real conversation pauses are
preserved and turns are interleaved correctly — not all-AI-then-all-user.
Chunks whose inter-arrival gap (after accounting for the previous chunk's
audio duration) falls below 50 ms are treated as contiguous (processing jitter
is never turned into artificial silence).

Mixing is done by safe int32 summation with int16 clipping, so simultaneous
speech (barge-in / overlap) is preserved and never force-shifted.
"""

from __future__ import annotations

import struct
import subprocess
import threading
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from loguru import logger

from config import settings


import time

_SR = 16000
_BPS = 2  # bytes per sample (s16le)

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


def mix_pcm_s16le(a: bytes, b: bytes) -> bytes:
    """Mix two mono s16le PCM streams without wraparound or clipping distortion.

    Sums in int32 and clips to int16.  When only one stream carries signal (the
    normal case in a phone conversation) loudness is preserved exactly; clipping
    can only occur during genuine simultaneous speech, which is brief and
    inaudible.  ``audioop.add`` was avoided because it hard-clips the same way
    but offers no room to reason about overlap.
    """
    if not a:
        return b
    if not b:
        return a
    if len(a) != len(b):
        n = max(len(a), len(b))
        a = a + b"\x00" * (n - len(a))
        b = b + b"\x00" * (n - len(b))
    an = np.frombuffer(a, dtype=np.int16).astype(np.int32)
    bn = np.frombuffer(b, dtype=np.int16).astype(np.int32)
    s = an + bn
    np.clip(s, -32768, 32767, out=s)
    return s.astype(np.int16).tobytes()


class CallRecorder:
    """Accumulates per-direction, sequence-ordered PCM and writes WAV/MP3 on close.

    ``add_inbound`` / ``add_outbound`` append PCM to a continuous per-direction
    timeline.  Every frame is tagged with a monotonic sequence number and an
    arrival timestamp that is used **only for diagnostics** — the audio position
    is derived purely from frame order and accumulated sample count.

    On ``close()`` the recorder hands the queued frames to a background worker
    thread, which writes three artifacts:

    * ``<stem>_inbound.wav``  — customer timeline (continuous, no gaps)
    * ``<stem>_outbound.wav`` — AI timeline (continuous, no gaps)
    * ``<stem>_mixed.wav/.mp3`` — the two timelines merged with **gap-aware**
      alignment: silence gaps are reconstructed from inter-chunk arrival
      timestamps so that real conversation pauses are preserved and turns
      are interleaved correctly (not all-AI-then-all-user).
    """

    def __init__(self, session_id: str, *, channel: str, base_dir: Optional[str] = None) -> None:
        self._session_id = session_id
        self._channel = channel
        self._lock = threading.Lock()
        self._in_path: Optional[str] = None
        self._out_path: Optional[str] = None

        # Continuous per-direction streams.  Each entry is
        # (sequence_number, pcm_bytes, arrival_timestamp).
        self._in_chunks: list[tuple[int, bytes, float]] = []
        self._out_chunks: list[tuple[int, bytes, float]] = []
        self._in_seq: int = 0
        self._out_seq: int = 0
        self._in_samples: int = 0
        self._out_samples: int = 0

        # Arrival-time diagnostics — never used to place audio.
        self._in_first_arrival: Optional[float] = None
        self._out_first_arrival: Optional[float] = None
        self._in_last_arrival: Optional[float] = None
        self._out_last_arrival: Optional[float] = None
        self._in_arrival_jitter_ms: list[float] = []
        self._out_arrival_jitter_ms: list[float] = []

        # Reference anchor: the Vobiz stream start time (perf_counter).  Used
        # only as a coarse alignment reference between the two timelines.
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

        logger.info(
            "Call recording: initialized channel={} session={} in={} out={}",
            channel,
            session_id,
            self._in_path,
            self._out_path,
        )

    def set_stream_start(self, t: Optional[float] = None) -> None:
        """Set the Vobiz stream start reference time for coarse alignment."""
        self._stream_start_t = t if t is not None else time.perf_counter()

    def add_inbound(self, pcm_s16le_mono: bytes, seq: Optional[int] = None) -> None:
        """Append inbound PCM to the customer timeline (ordered, contiguous)."""
        self._append("in", pcm_s16le_mono, seq)

    def add_outbound(self, pcm_s16le_mono: bytes, seq: Optional[int] = None) -> None:
        """Append outbound PCM to the AI timeline (ordered, contiguous)."""
        self._append("out", pcm_s16le_mono, seq)

    def _append(self, direction: str, pcm: bytes, seq: Optional[int]) -> None:
        if not pcm:
            return
        if direction == "in":
            if not self._in_path:
                return
        else:
            if not self._out_path:
                return

        now = time.perf_counter()
        with self._lock:
            if direction == "in":
                if seq is None:
                    seq = self._in_seq
                self._in_seq = max(self._in_seq, seq + 1)
                if self._in_first_arrival is None:
                    self._in_first_arrival = now
                if self._in_last_arrival is not None:
                    self._in_arrival_jitter_ms.append((now - self._in_last_arrival) * 1000.0)
                self._in_last_arrival = now
                self._in_chunks.append((seq, bytes(pcm), now))
                self._in_samples += len(pcm) // 2
            else:
                if seq is None:
                    seq = self._out_seq
                self._out_seq = max(self._out_seq, seq + 1)
                if self._out_first_arrival is None:
                    self._out_first_arrival = now
                if self._out_last_arrival is not None:
                    self._out_arrival_jitter_ms.append((now - self._out_last_arrival) * 1000.0)
                self._out_last_arrival = now
                self._out_chunks.append((seq, bytes(pcm), now))
                self._out_samples += len(pcm) // 2

    def close(self) -> None:
        if self._in_path or self._out_path:
            logger.info(
                "Call recording: closing channel={} session={} (in_chunks={} out_chunks={})",
                self._channel,
                self._session_id,
                len(self._in_chunks),
                len(self._out_chunks),
            )
            threading.Thread(target=self._write_recording, daemon=True).start()

    def recording_depth(self) -> int:
        """Number of queued frames still pending finalization (diagnostics)."""
        return len(self._in_chunks) + len(self._out_chunks)

    def recording_drop_count(self) -> int:
        """Frames dropped by the recording path (always 0 in the new pipeline)."""
        return 0

    # ------------------------------------------------------------------ #
    # Gap-aware timeline builder                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_timeline_from_chunks(
        chunks: list[tuple[int, bytes, float]],
        anchor: float,
        gap_threshold_sec: float = 0.05,
    ) -> bytes:
        """Build a PCM timeline with silence gaps based on arrival timestamps.

        Unlike simple concatenation, this preserves real conversation rhythm
        by inserting silence where the speaker was actually silent.  Chunks
        whose inter-arrival gap (after accounting for the previous chunk's
        audio duration) falls below ``gap_threshold_sec`` are treated as
        contiguous — processing jitter is never turned into artificial silence.

        Each chunk is ``(seq, pcm_bytes, arrival_perf_counter)``.
        ``anchor`` is the earliest known event time (stream start or first
        chunk arrival across both directions).
        """
        if not chunks:
            return b""

        result = bytearray()
        prev_end_time: Optional[float] = None

        for _seq, pcm, arrival in chunks:
            if prev_end_time is None:
                # First chunk: position relative to anchor.
                lead_sec = arrival - anchor
                if lead_sec > gap_threshold_sec:
                    lead_samples = int(lead_sec * _SR)
                    result.extend(b"\x00\x00" * lead_samples)
            else:
                # Subsequent chunk: insert silence for real conversation gap.
                gap_sec = arrival - prev_end_time
                if gap_sec > gap_threshold_sec:
                    gap_samples = int(gap_sec * _SR)
                    result.extend(b"\x00\x00" * gap_samples)

            result.extend(pcm)
            chunk_duration = len(pcm) / (_SR * _BPS)
            prev_end_time = arrival + chunk_duration

        return bytes(result)

    # ------------------------------------------------------------------ #
    # Audio shaping (unchanged helpers)                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _noise_gate(pcm: bytes) -> bytes:
        """Suppress low-level hiss floor from telephony audio.

        Computes RMS in 20 ms windows and applies smooth gain reduction when
        the level falls below ``_NOISE_GATE_THRESH``.  Attack/release envelopes
        prevent the gain changes from sounding choppy.  This targets the
        broadband hiss that Vobiz/SIP gateways inject on both legs without
        touching actual speech.
        """
        n = len(pcm) // 2
        if n < 2:
            return pcm
        win = int(_SR * 0.02)  # 20 ms window
        if win < 2:
            win = 2
        arr = bytearray(pcm)
        max_i16 = 32768.0
        thresh = _NOISE_GATE_THRESH
        reduction = _NOISE_GATE_REDUCTION
        attack = _NOISE_GATE_ATTACK_SAMPLES
        release = _NOISE_GATE_RELEASE_SAMPLES
        # Per-sample gain envelope, smoothed across windows.
        gain = 1.0
        pos = 0
        while pos < n:
            end = min(pos + win, n)
            # RMS of this window
            total = 0.0
            for i in range(pos, end):
                s = struct.unpack_from("<h", arr, i * 2)[0]
                total += s * s
            rms = (total / (end - pos)) ** 0.5 / max_i16
            target = 1.0 if rms > thresh else reduction
            # Smoothly move gain toward target across the window.
            if target < gain:
                step = (gain - target) / max(1, release)
            else:
                step = (target - gain) / max(1, attack)
            for i in range(pos, end):
                gain = max(reduction, min(1.0, gain + step)) if target > gain else max(reduction, gain - step)
                v = struct.unpack_from("<h", arr, i * 2)[0]
                struct.pack_into("<h", arr, i * 2, int(v * gain))
            pos = end
        return bytes(arr)

    @staticmethod
    def _trim_trailing_silence(pcm: bytes, keep_ms: float = 350.0) -> bytes:
        """Drop trailing digital-silence padding, keeping a short tail window.

        Live call audio often ends minutes after the last speech burst (Vobiz
        keeps the stream open until hangup); without this the WAV/MP3 contains
        long runs of dead air that make the recording feel bloated.
        """
        n = len(pcm) // 2
        if n < 2:
            return pcm
        keep = int(_SR * keep_ms / 1000.0)
        idx = n - 1
        while idx >= 0:
            if abs(struct.unpack_from("<h", pcm, idx * 2)[0]) > 40:
                break
            idx -= 1
        idx = min(n - 1, idx + keep)
        return pcm[: idx * 2 + 2]

    # ------------------------------------------------------------------ #
    # Worker (background thread — never on the live call path)           #
    # ------------------------------------------------------------------ #

    def _write_recording(self) -> None:
        t_start = time.perf_counter()
        with self._lock:
            in_chunks = list(self._in_chunks)
            out_chunks = list(self._out_chunks)
            self._in_chunks.clear()
            self._out_chunks.clear()
            in_first = self._in_first_arrival
            out_first = self._out_first_arrival
            stream_start = self._stream_start_t
            in_jitter = list(self._in_arrival_jitter_ms)
            out_jitter = list(self._out_arrival_jitter_ms)

        # Build contiguous per-direction streams for individual WAVs.
        # Order is preserved; NO silence is inserted for inter-frame arrival
        # gaps (network jitter is not conversational silence).
        in_pcm = b"".join(pcm for _, pcm, _ in in_chunks)
        out_pcm = b"".join(pcm for _, pcm, _ in out_chunks)

        if self._in_path and in_pcm:
            self._write_wav(
                self._in_path,
                self._noise_gate(self._trim_trailing_silence(in_pcm)),
                "inbound",
            )

        if self._out_path and out_pcm:
            self._write_wav(
                self._out_path,
                self._noise_gate(self._trim_trailing_silence(out_pcm)),
                "outbound",
            )

        if in_pcm or out_pcm:
            # Build gap-aware timelines for the MIXED recording so real
            # conversation pauses are preserved and turns are interleaved
            # correctly (not all-AI-then-all-user).
            anchors: list[float] = []
            if stream_start is not None:
                anchors.append(stream_start)
            if in_first is not None:
                anchors.append(in_first)
            if out_first is not None:
                anchors.append(out_first)
            anchor = min(anchors) if anchors else 0.0

            in_timeline = self._build_timeline_from_chunks(in_chunks, anchor)
            out_timeline = self._build_timeline_from_chunks(out_chunks, anchor)
            self._write_mixed(in_timeline, out_timeline)

        self._log_diagnostics(in_chunks, out_chunks, in_jitter, out_jitter, t_start)

    def _write_wav(self, path: str, pcm: bytes, label: str) -> None:
        try:
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(_SR)
                w.writeframes(pcm)
            logger.info(
                "Call recording: {} WAV written {} ({} B, {:.1f}s)",
                label,
                path,
                len(pcm),
                len(pcm) / (_SR * _BPS),
            )
        except Exception as e:
            logger.exception("Call recording: failed to write {} WAV {}: {}", label, path, e)

    def _write_mixed(
        self,
        in_timeline: bytes,
        out_timeline: bytes,
    ) -> None:
        if not in_timeline and not out_timeline:
            return

        # Both timelines share the same anchor so they are already aligned.
        # Just pad the shorter one with silence to equal length and mix.
        max_len = max(len(in_timeline), len(out_timeline))
        in_padded = in_timeline + b"\x00" * (max_len - len(in_timeline))
        out_padded = out_timeline + b"\x00" * (max_len - len(out_timeline))

        mixed = mix_pcm_s16le(in_padded, out_padded)
        mixed = self._noise_gate(self._trim_trailing_silence(mixed))

        stem = Path(self._in_path or self._out_path).stem
        for suffix in ("_inbound", "_outbound"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break

        mixed_path = str(Path(self._in_path or self._out_path).parent / f"{stem}_mixed.wav")
        try:
            with wave.open(mixed_path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(_SR)
                w.writeframes(mixed)
            logger.info(
                "Call recording: mixed WAV written {} ({} B, {:.1f}s)",
                mixed_path,
                len(mixed),
                len(mixed) / (_SR * _BPS),
            )

            mp3_path = mixed_path.replace(".wav", ".mp3")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", mixed_path, "-acodec", "libmp3lame", "-b:a", "64k", mp3_path],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("Call recording: compressed to MP3 {}", mp3_path)
                Path(mixed_path).unlink(missing_ok=True)
            except Exception as ffmpeg_err:
                logger.warning("Call recording: MP3 compression failed: {}", ffmpeg_err)
        except Exception as e:
            logger.exception("Call recording mix failed: {}", e)

    # ------------------------------------------------------------------ #
    # Diagnostics                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _jitter_stats(jitter_ms: list[float]) -> tuple[float, float]:
        if not jitter_ms:
            return 0.0, 0.0
        return sum(jitter_ms) / len(jitter_ms), max(jitter_ms)

    @staticmethod
    def _sequence_gaps(chunks: list[tuple[int, bytes, float]]) -> int:
        """Count genuine missing-frame gaps (sequence numbers that skip)."""
        if not chunks:
            return 0
        gaps = 0
        prev = chunks[0][0]
        for seq, _, _ in chunks[1:]:
            if seq > prev + 1:
                gaps += 1
            prev = seq
        return gaps

    def _log_diagnostics(
        self,
        in_chunks: list[tuple[int, bytes, float]],
        out_chunks: list[tuple[int, bytes, float]],
        in_jitter: list[float],
        out_jitter: list[float],
        t_start: float,
    ) -> None:
        in_avg, in_max = self._jitter_stats(in_jitter)
        out_avg, out_max = self._jitter_stats(out_jitter)
        logger.info(
            "CALL-RECORDING-DIAG session={} channel={} "
            "frames_in={} frames_out={} "
            "seq_gaps_in={} seq_gaps_out={} "
            "arrival_jitter_in={:.1f}/{:.1f}ms arrival_jitter_out={:.1f}/{:.1f}ms "
            "processing_time={:.0f}ms",
            self._session_id,
            self._channel,
            len(in_chunks),
            len(out_chunks),
            self._sequence_gaps(in_chunks),
            self._sequence_gaps(out_chunks),
            in_avg,
            in_max,
            out_avg,
            out_max,
            (time.perf_counter() - t_start) * 1000.0,
        )

    def meta(self) -> dict[str, Any]:
        return {
            "inbound_wav": self._in_path,
            "outbound_wav": self._out_path,
            "call_recording": bool(self._in_path or self._out_path),
            "total_chunks": len(self._in_chunks) + len(self._out_chunks),
            "inbound_frames": len(self._in_chunks),
            "outbound_frames": len(self._out_chunks),
            "inbound_samples": self._in_samples,
            "outbound_samples": self._out_samples,
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
