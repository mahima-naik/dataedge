from __future__ import annotations

import json
import os
import time
import base64
from pathlib import Path

import httpx
from loguru import logger

from config import settings

def _recording_dirs() -> list[Path]:
    """Resolve all recording directories to search."""
    dirs = []
    # Primary: settings.call_recording_dir (e.g., data/recordings from .env)
    primary = Path(settings.call_recording_dir)
    if not primary.is_absolute():
        primary = (Path(__file__).resolve().parent.parent / primary).resolve()
    else:
        primary = primary.resolve()
    if primary.is_dir():
        dirs.append(primary)
    # Fallback: legacy data/recordings flat directory
    legacy = Path(__file__).resolve().parent.parent / "data" / "recordings"
    if legacy.is_dir() and legacy.resolve() != primary.resolve():
        dirs.append(legacy)
    return dirs


def _find_date_dir(log_id: str) -> Path | None:
    """Find the date subdirectory containing recordings for this log_id."""
    for base in _recording_dirs():
        if not base.is_dir():
            continue
        # Check flat files at root level first
        for f in base.iterdir():
            if f.is_file() and log_id in f.name:
                return base
        # Check date subdirectories
        for date_part in sorted(p.name for p in base.iterdir() if p.is_dir() and len(p.name) == 10):
            date_dir = base / date_part
            if any(log_id in str(f.name) for f in date_dir.iterdir()):
                return date_dir
    return None


async def transcribe_audio(log_id: str, role: str = "data_edge") -> str | None:
    date_dir = _find_date_dir(log_id)
    if not date_dir:
        logger.warning(f"No recording directory found for log_id={log_id}")
        return None

    # Prefer MP3 over WAV
    fp = date_dir / f"{log_id}_mixed.mp3"
    mime_type = "audio/mp3"
    if not fp.is_file():
        fp = date_dir / f"{log_id}_mixed.wav"
        mime_type = "audio/wav"

    if not fp.is_file():
        logger.warning(f"No transcribable audio found for log_id={log_id}")
        return None

    mb = fp.stat().st_size / (1024 * 1024)
    logger.info(f"Transcribing {fp.name} ({mb:.1f} MB) with Gemini...")
    t0 = time.time()

    key = (settings.gemini_api_key or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY is not set for transcription")

    model = settings.gemini_call_analysis_model or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

    with open(fp, "rb") as f:
        audio_data = f.read()
    
    b64_audio = base64.b64encode(audio_data).decode("utf-8")

    prompt = (
        "Transcribe the following phone call conversation. "
        "There are two speakers: an AI 'assistant' and a human 'user'. "
        "Return a valid JSON array of objects, where each object has "
        "a 'role' (either 'user' or 'assistant') and a 'content' (the transcribed text spoken). "
        "Output ONLY valid JSON."
    )

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": b64_audio
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(url, json=body)
        
    if r.status_code != 200:
        logger.error(f"Gemini transcription failed: {r.status_code} {r.text}")
        return None

    data = r.json()
    cands = data.get("candidates") or []
    if not cands:
        logger.error(f"Gemini transcription no candidates: {data}")
        return None

    raw_json = ""
    for part in (cands[0].get("content") or {}).get("parts") or []:
        raw_json += part.get("text", "")
    
    try:
        tagged = json.loads(raw_json)
        if not isinstance(tagged, list):
            tagged = [{"role": "user", "content": raw_json}]
    except Exception as e:
        logger.error(f"Failed to parse Gemini transcription JSON: {e}")
        tagged = [{"role": "user", "content": raw_json}]

    dt = time.time() - t0
    logger.info(f"Transcription completed in {dt:.1f}s ({len(tagged)} total segments)")

    # Build JSONL content
    jsonl_lines = [json.dumps(t) for t in tagged if isinstance(t, dict)]
    jsonl_text = "\n".join(jsonl_lines)

    # Save to the logs directory where _read_transcript_jsonl looks
    from datetime import datetime, timezone
    backend_dir = Path(__file__).resolve().parent.parent
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_dir = backend_dir / "data" / role / "logs" / date_str
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = log_dir / f"{log_id}.jsonl"
    with open(str(jsonl_path), "w") as f:
        f.write(jsonl_text)

    logger.info(f"Transcript saved to {jsonl_path}")
    return jsonl_text

