"""Shared transcript QA prompt + JSON parsing for call analysis backends."""

from __future__ import annotations

import json
import re
from datetime import datetime

from loguru import logger
from config import settings
from services.callback_time import zoneinfo_safe


def empty_transcript_result(*, summary: str, rationale: str) -> dict:
    return {
        "summary": summary,
        "rating": 0,
        "next_steps": "N/A",
        "disposition": "Answered",
        "emotion_label": "Unknown",
        "emotion_rationale": rationale,
        "emotion_confidence": None,
        "requested_callback_datetime_iso": None,
    }


def _try_parse(s: str) -> dict | None:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    try:
        fixed = re.sub(r",\s*}", "}", s)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    return None


def parse_json_from_text(text: str) -> dict | None:
    raw = text.strip()
    if not raw:
        return None

    # 1. direct parse
    parsed = _try_parse(raw)
    if parsed:
        return parsed

    # 2. extract from markdown code blocks
    if "```" in raw:
        blob = raw
        if "```json" in blob:
            blob = blob.split("```json", 1)[-1]
        elif "```" in blob:
            blob = blob.split("```", 1)[-1]
        blob = blob.split("```", 1)[0].strip()
        parsed = _try_parse(blob)
        if parsed:
            return parsed

    # 3. extract first {…} block
    brace0 = raw.find("{")
    brace1 = raw.rfind("}")
    if brace0 >= 0 and brace1 > brace0:
        candidate = raw[brace0 : brace1 + 1]
        parsed = _try_parse(candidate)
        if parsed:
            return parsed

    # 4. truncated JSON — missing closing }
    if brace0 >= 0:
        candidate = raw[brace0:]
        if not candidate.endswith("}"):
            candidate += "}"
            parsed = _try_parse(candidate)
            if parsed:
                return parsed

    logger.warning("parse_json_from_text all attempts failed ({} chars): {}", len(raw), raw[:240])
    return None


def _safe_int(v, default=0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def result_from_json(result: dict) -> dict:
    iso_cb = result.get("requested_callback_datetime_iso")
    if isinstance(iso_cb, str):
        iso_cb = iso_cb.strip() or None
    elif iso_cb is not None:
        iso_cb = None
    emotion_confidence = result.get("emotion_confidence")
    if emotion_confidence is not None:
        try:
            emotion_confidence = float(emotion_confidence)
        except Exception:
            emotion_confidence = None
    
    # Handle the old next_steps array or string fallback
    next_steps = result.get("next_steps", "N/A")
    if isinstance(next_steps, list):
        next_steps = "; ".join(str(x).strip() for x in next_steps if str(x).strip()) or "N/A"
        
    next_action_obj = result.get("next_action") or {}
    action_type = next_action_obj.get("action_type") or "None"
    action_datetime_iso = next_action_obj.get("action_datetime_iso")
    action_details = next_action_obj.get("details") or ""
        
    return {
        "summary": result.get("summary", "Analysis failed"),
        "rating": _safe_int(result.get("rating", 0)),
        "next_steps": next_steps,
        "next_action": {
            "type": action_type,
            "datetime_iso": action_datetime_iso,
            "details": action_details
        },
        "disposition": result.get("disposition", "Answered"),
        "emotion_label": result.get("emotion_label", "Unknown"),
        "emotion_rationale": result.get("emotion_rationale", ""),
        "emotion_confidence": emotion_confidence,
        "requested_callback_datetime_iso": iso_cb,
    }


def build_analysis_prompt(transcript_text: str) -> str:
    lines = []
    for line in transcript_text.splitlines():
        try:
            obj = json.loads(line)
            role = obj.get("role") or obj.get("type", "")
            content = obj.get("content") or obj.get("text") or obj.get("message", "")
            if role in ("user", "assistant") and content:
                lines.append(f"{role.capitalize()}: {content.strip()}")
        except Exception:
            continue

    if not lines:
        return ""

    readable_chat = "\n".join(lines)

    tz_name = settings.transcript_callback_tz.strip().lower()
    tz_display = settings.transcript_callback_tz.strip()
    if tz_name in ("asia/kolkata", "asia/calcutta"):
        tz_display = "Indian Standard Time — Asia/Kolkata (IST, UTC+05:30)"

    tz = zoneinfo_safe(settings.transcript_callback_tz)
    local_now = datetime.now(tz)
    sched_ctx = (
        f"Scheduling zone: {tz_display}. "
        f"Local 'now' is {local_now.isoformat(timespec='minutes')} "
        f"in THAT zone."
    )

    return f"""You are a QA analyst reviewing a sales call transcript.
Your ONLY output must be a valid, raw JSON object. Do not include any introductory text, bullet points, or explanations. Start immediately with {{ and end with }}.

You must return a JSON object with EXACTLY these keys:
- "summary": 1-2 sentence summary of what happened on the call
- "rating": integer 1-5 (quality of engagement)
- "next_steps": concrete follow-up actions for the sales team (string or array of strings)
- "next_action": An object describing the primary structured next action the system or agent should take. Must contain:
  - "action_type": exactly one of ["WhatsApp", "Email", "Call Again", "None", "Other"]
  - "action_datetime_iso": RFC3339 datetime with offset if a specific time was agreed upon for the action, else null
  - "details": Detailed explanation of what exactly to send, say, or do.
- "disposition": one of ["Interested", "Not Interested", "Call Later", "Busy", "Answered", "Wrong Number"]
  Rules for disposition:
  - "Interested": Mark Interested ONLY when the conversation clearly demonstrates genuine interest in the course/program. Genuine interest requires a meaningful and reasonably complete conversation where the customer:
    * Engages with the counselor about their career/learning needs
    * Shows genuine interest in one or more DataEdge programs
    * Discusses their goals, requirements, or reasons for considering the course
    * Responds positively to the course/program explanation or recommendation
    * Shows intent to explore the program further, AND/OR
    * Takes a meaningful next step because of that interest
    Examples that ARE Interested (genuine interest in the course is clear):
    * "Yes, I'm interested in the Data Analytics course."
    * "I want to learn AI because I'm looking for a career change."
    * "This course sounds relevant to me. Can you explain the details?"
    * "I'm interested. Send me the brochure and I'll go through it."
    * "I need some time to discuss it, but I am interested in the course."
    * "Can you send me the details? I'll review them and get back to you."
    * "I'm interested in the program. You can call me later."
    * "I want to know more about the course and its curriculum."
    * "I'm interested in the AI course. I have a meeting now, so call me tomorrow."
  - "Interested" (hesitation about TIMING, not interest): a customer who already demonstrated genuine interest in the course earlier in the conversation and then says "I'm interested, but I need some time. I'll let you know later" or "The course is relevant to me. Send me the brochure and I'll discuss it and get back to you" IS Interested — the hesitation is about timing/decision-making, not lack of interest.
  - "Not Interested": only clear, direct rejection. "Stop calling", "take me off your list", "not interested" said firmly. Do NOT treat soft/mild responses as Not Interested.
  - Do NOT mark Interested merely because the customer (these are weak signals, NOT sufficient on their own):
    * Asks for a WhatsApp brochure, course details, or a demo
    * Agrees to receive information on WhatsApp/email
    * Says "send me the details" or "I'll check and let you know"
    * Asks for a callback without showing genuine interest in the course
    * Gives a polite or non-committal response
    * Says "I'll let you know later" WITHOUT having already demonstrated genuine course interest
  - "Answered": use when there was no meaningful sales conversation or only weak/non-committal signals with NO demonstrated genuine interest (e.g. a bare "send me the brochure" with no course engagement, IVR only, wrong person with no contact request, callee never engaged, or a language barrier where the customer's question was not addressed).
  - "Call Later": prospect explicitly asks to be called at a future time/date.
  - "Busy": prospect says they are busy right now without scheduling a callback.
  - "Wrong Number": prospect says wrong number / person doesn't exist.
  - CRITICAL: Consider the ENTIRE conversation, not a single sentence or keyword. Keywords like "brochure", "WhatsApp", "demo", "callback", "details", "later", "interested" are NOT sufficient on their own. Before marking Interested, ask: "Based on the complete conversation, has the customer genuinely shown interest in pursuing or seriously exploring a DataEdge course/program?" If YES → Interested. If NO or UNCLEAR → do NOT mark Interested. Never inflate the interested count.
- "emotion_label": one of ["Positive", "Neutral", "Skeptical", "Frustrated", "Confused", "Angry", "Unknown"]
- "emotion_confidence": number 0.0-1.0
- "emotion_rationale": one sentence explaining the callee's emotional tone
- "requested_callback_datetime_iso": RFC3339 datetime with offset if callee requested a callback time, else null

{sched_ctx}

TRANSCRIPT:
{readable_chat}

CRITICAL INSTRUCTION: Do NOT output bullet points, do NOT output your role, and do NOT output markdown code blocks. Output NOTHING but the raw JSON object itself, starting with {{ and ending with }}. Ensure the JSON is valid with no trailing commas.
"""
