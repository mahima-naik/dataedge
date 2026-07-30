"""PCM helpers, optional background decode, and pacing outbound ``playAudio`` frames."""

from __future__ import annotations

import audioop
import base64
import json
from typing import Optional

import numpy as np
from fastapi import WebSocket
from loguru import logger

from .constants import OUT_CHUNK_BYTES, VOBIZ_CONTENT_TYPE, VOBIZ_SR

try:
    import miniaudio
except ImportError:
    miniaudio = None

from services.call_recording import CallRecorder


_LPF_TAPS: np.ndarray | None = None
_FILTER_DELAY: int = 64  # samples at 24kHz (filter length - 1)


def _lpf_ensure() -> None:
    global _LPF_TAPS
    if _LPF_TAPS is not None:
        return
    nyq = 24000 / 2.0
    fc = 7200.0 / nyq
    n = np.arange(65) - 32.0
    h = np.sinc(2 * fc * n)
    h *= np.kaiser(65, 5.0)
    h /= h.sum()
    _LPF_TAPS = h.astype(np.float64)


def resample_24k_to_16k_numpy(pcm_24k: bytes, state: dict | None = None) -> tuple[bytes, dict]:
    """Resample 24kHz mono s16le PCM to 16kHz via overlap-save FIR + linear interpolation.

    Anti-aliasing cutoff at 7.2kHz (65-tap Kaiser windowed-sinc) eliminates the
    harsh/metallic artifacts from ``audioop.ratecv``.

    The ``state`` dict holds the last ``_FILTER_DELAY`` (64) **input** samples so
    overlap-save convolution produces exactly the right number of output samples
    per chunk — no timing drift.
    """
    if len(pcm_24k) < 4:
        return pcm_24k, state or {}
    _lpf_ensure()

    in_tail: np.ndarray | None = (state or {}).get("in_tail")
    src = np.frombuffer(pcm_24k, dtype=np.int16).astype(np.float64)
    src_len = len(src)

    # Overlap-save: prepend last chunk's input tail
    if in_tail is not None and len(in_tail) > 0:
        padded = np.concatenate([in_tail, src])
    else:
        pad = src[:_FILTER_DELAY][::-1] if src_len >= _FILTER_DELAY else np.full(_FILTER_DELAY, src[0])
        padded = np.concatenate([pad, src])

    # Save last _FILTER_DELAY input samples for next chunk
    new_tail = src[-_FILTER_DELAY:].copy() if src_len >= _FILTER_DELAY else src.copy()

    # Overlap-save FIR: output has exactly src_len samples
    filtered = np.convolve(padded, _LPF_TAPS, mode="valid")
    # len(filtered) = len(padded) - _FILTER_DELAY = src_len

    # Linear interpolation to 16kHz
    out_len = int(src_len * 16000 / 24000)
    if out_len < 1:
        return b"", {"in_tail": new_tail}
    indices = np.linspace(0, src_len - 1, out_len)
    x0 = np.floor(indices).astype(np.int64)
    x1 = np.minimum(x0 + 1, src_len - 1)
    frac = indices - x0
    out = filtered[:src_len][x0] * (1.0 - frac) + filtered[:src_len][x1] * frac
    out = np.clip(out, -32768, 32767).astype(np.int16)
    return out.tobytes(), {"in_tail": new_tail}


def load_background_audio(path: str, target_sr: int = 16000) -> Optional[np.ndarray]:
    if miniaudio is None or not path or not __import__("os").path.exists(path):
        return None
    try:
        decoded = miniaudio.decode_file(path, sample_rate=target_sr, nchannels=1)
        return np.frombuffer(decoded.samples, dtype=np.int16)
    except Exception as e:
        logger.error(f"Failed to load background audio: {e}")
        return None


def pcm_rms_norm(pcm: np.ndarray) -> float:
    if pcm.size == 0:
        return 0.0
    x = pcm.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(np.square(x))))


def pcm_resample(pcm_bytes: bytes, in_sr: int, out_sr: int) -> bytes:
    if in_sr == out_sr:
        return pcm_bytes
    out, _ = audioop.ratecv(pcm_bytes, 2, 1, in_sr, out_sr, None)
    return out


def mix_voice_and_background_tick(
    voice_pcm16: bytes,
    bg_wave: Optional[np.ndarray],
    volume: float,
    bg_position: int,
    chunk_samples: int,
) -> tuple[bytes, int]:
    """One 16-bit mono tick: blend outbound voice with a looped bed (scripted PCM or Gemini).

    ``volume`` scales the bed linearly on float samples before clipping (e.g. 0.75 ≈ 75 %).
    """
    chunk_bytes = chunk_samples * 2
    bg_pcm = None
    vol = float(volume)
    if vol < 0.0:
        vol = 0.0
    if bg_wave is not None and vol > 0:
        end_pos = bg_position + chunk_samples
        if end_pos > len(bg_wave):
            part1 = bg_wave[bg_position:]
            part2 = bg_wave[: end_pos - len(bg_wave)]
            bg_chunk = np.concatenate((part1, part2))
            bg_position = end_pos - len(bg_wave)
        else:
            bg_chunk = bg_wave[bg_position:end_pos]
            bg_position = end_pos

        bg_chunk = (bg_chunk.astype(np.float32) * vol).clip(-32768, 32767).astype(np.int16)
        bg_pcm = bg_chunk.tobytes()

    if bg_pcm is None:
        return voice_pcm16, bg_position
    if not voice_pcm16:
        return bg_pcm, bg_position
    mixed = audioop.add(voice_pcm16, bg_pcm, 2)
    return mixed, bg_position


def pop_l16_chunk(queue: bytearray, chunk_bytes: int) -> bytes:
    if len(queue) >= chunk_bytes:
        out = bytes(queue[:chunk_bytes])
        del queue[:chunk_bytes]
        return out
    if len(queue) > 0:
        n = len(queue)
        out = bytes(queue) + b"\x00" * (chunk_bytes - n)
        queue.clear()
        return out
    return b"\x00" * chunk_bytes


_PLAY_TPL = (
    '{"event":"playAudio","media":{"contentType":"'
    + VOBIZ_CONTENT_TYPE
    + '","sampleRate":16000,"payload":"'
)
_PLAY_END = '"}}'


async def send_play_audio(
    ws: WebSocket,
    pcm16_bytes: bytes,
    sr: int = VOBIZ_SR,
    *,
    call_recorder: Optional[CallRecorder] = None,
) -> None:
    if not pcm16_bytes:
        return
    if call_recorder is not None:
        call_recorder.add_outbound(pcm16_bytes)
    view = memoryview(pcm16_bytes)
    for offset in range(0, len(view), OUT_CHUNK_BYTES):
        chunk = bytes(view[offset : offset + OUT_CHUNK_BYTES])
        if len(chunk) < 2:
            continue
        await ws.send_text(_PLAY_TPL + base64.b64encode(chunk).decode("ascii") + _PLAY_END)


async def send_play_audio_batched(
    ws: WebSocket,
    pcm16_bytes: bytes,
    sr: int = VOBIZ_SR,
) -> None:
    """Send PCM audio as a single WebSocket message.

    Unlike ``send_play_audio`` which splits into 640-byte chunks (one WS frame
    per 20 ms), this sends the entire buffer in one ``playAudio`` message.  On a
    2-core VPS where each ``ws.send_text()`` blocks for ~280 ms, batching 8
    frames (160 ms, 5120 bytes) into one send cuts outbound traffic by ~8x and
    keeps the mixer close to real-time.
    """
    if not pcm16_bytes:
        return
    await ws.send_text(
        _PLAY_TPL + base64.b64encode(pcm16_bytes).decode("ascii") + _PLAY_END
    )
