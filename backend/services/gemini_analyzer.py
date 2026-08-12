"""Post-call transcript QA via Google AI Studio (Gemini API key)."""

from __future__ import annotations

import os
import time

import httpx
from loguru import logger

from config import settings
from services.analysis_prompt import (
    build_analysis_prompt,
    empty_transcript_result,
    parse_json_from_text,
    result_from_json,
)
from services.gemini_tts import normalize_gemini_model


async def analyze_gemini(transcript_text: str) -> dict:
    if not transcript_text.strip():
        return empty_transcript_result(
            summary="No transcript available",
            rationale="",
        )

    prompt = build_analysis_prompt(transcript_text)
    if not prompt:
        return empty_transcript_result(
            summary="Call ended early / No conversation",
            rationale="No conversational turns in transcript.",
        )

    key = (settings.gemini_call_analysis_api_key or "").strip()
    if not key:
        raise RuntimeError("GEMINI_CALL_ANALYSIS_API_KEY / GEMINI_API_KEY is not set")

    model = normalize_gemini_model(settings.gemini_call_analysis_model or "gemini-2.0-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.15,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }

    import asyncio

    t0 = time.time()
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
                r = await client.post(url, json=body)
            if r.status_code == 200:
                break
            if r.status_code == 503 and attempt < max_attempts:
                sleep_sec = 2 * attempt
                logger.warning("Gemini analysis HTTP {} on attempt {}/{} - retrying in {}s...", r.status_code, attempt, max_attempts, sleep_sec)
                await asyncio.sleep(sleep_sec)
                continue
            raise RuntimeError(f"Gemini analysis HTTP {r.status_code}: {r.text[:800]}")
        except httpx.HTTPError as he:
            if attempt < max_attempts:
                sleep_sec = 2 * attempt
                logger.warning("Gemini analysis connection error on attempt {}/{} - retrying in {}s: {}", attempt, max_attempts, sleep_sec, he)
                await asyncio.sleep(sleep_sec)
                continue
            raise he

    data = r.json()
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini analysis: no candidates: {str(data)[:600]}")

    parts = (cands[0].get("content") or {}).get("parts") or []
    raw = ""
    for part in parts:
        raw += str(part.get("text") or "")
    raw = raw.strip()
    if not raw:
        raise RuntimeError("Gemini analysis: empty text in response")

    logger.info(
        "Gemini call analysis done model={} in {:.1f}s ({} chars)",
        model,
        time.time() - t0,
        len(raw),
    )

    parsed = parse_json_from_text(raw)
    if parsed:
        return result_from_json(parsed)

    logger.warning("Gemini analysis JSON parse failed: {}", raw[:240])
    return {
        "summary": "Analysis parsing failed",
        "rating": 0,
        "next_steps": "Retry analysis",
        "disposition": "Answered",
        "emotion_label": "Unknown",
        "emotion_rationale": "",
        "emotion_confidence": None,
        "requested_callback_datetime_iso": None,
    }
