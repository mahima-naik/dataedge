from __future__ import annotations

import os

from loguru import logger

from config import settings


def _analysis_provider() -> str:
    return (os.getenv("CALL_ANALYSIS_PROVIDER") or "gemini").strip().lower()


async def analyze_call_transcript(transcript_text: str) -> dict:
    """Analyze call transcript — default: Gemini API (``GEMINI_API_KEY``)."""
    provider = _analysis_provider()

    if provider == "local":
        from services.local_analyzer import analyze_local

        return await analyze_local(transcript_text)

    key = (settings.gemini_api_key or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        logger.warning("No GEMINI_API_KEY — falling back to local analyzer")
        from services.local_analyzer import analyze_local

        return await analyze_local(transcript_text)

    from services.gemini_analyzer import analyze_gemini
    from services.analysis_throttle import throttled_gemini_call

    try:
        return await throttled_gemini_call(lambda: analyze_gemini(transcript_text))
    except Exception as e:
        logger.error("Gemini analysis failed: {}", e)
        raise


def canonical_disposition(raw: str | None) -> str:
    """Normalize analyzer-output disposition strings → stable buckets for SQLite status mapping."""

    text = str(raw or "").strip()
    if not text:
        return "Answered"

    lowered = " ".join(text.lower().replace("_", " ").split())

    ALLOWED_EXACT = {
        "Interested",
        "Not Interested",
        "Call Later",
        "Busy",
        "Answered",
        "Wrong Number",
        "Callback",
    }

    for label in ALLOWED_EXACT:
        if lowered == label.lower():
            return "Call Later" if label == "Callback" else label

    if "not interested" in lowered:
        return "Not Interested"
    if "wrong number" in lowered or "wrong no" in lowered:
        return "Wrong Number"
    if "no answer" in lowered or lowered == "no-answer":
        return "Answered"

    interested_hit = ("interested" in lowered) and "not interested" not in lowered
    if interested_hit:
        return "Interested"

    if lowered.startswith("busy") or lowered == "busy":
        return "Busy"
    if "call later" in lowered or lowered.startswith("callback"):
        return "Call Later"
    if lowered.startswith("answered") or lowered == "answer":
        return "Answered"

    return text.strip()
