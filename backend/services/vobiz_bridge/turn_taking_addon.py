"""Optional system-instruction appendix for Gemini Live duplex / interruption behavior."""

from __future__ import annotations

from config import settings

_LIVE_VOICE_TURN_ADDENDUM = """

[REALTIME PHONE INTERACTION — TURN-TAKING]
This is a live voice call — be warm, natural, and conversational.
HARD LIMIT: Every reply is MAX 1-2 short sentences (under 5 seconds of speech). Do NOT exceed this. Do NOT read script paragraphs verbatim.
If the scripts below are long, condense them into one brief sentence.
Complete your question before yielding, then STOP and listen.
If the callee speaks while you are talking, yield immediately and listen.
Always ask one relevant follow-up question, then stop.
CRITICAL: NEVER guess or invent the callee's name. If STT returns unclear text, do NOT treat random words as names. Only use a name after they clearly stated it. If unsure, say "Sorry, I didn't catch your name" and ask them to repeat.
"""


def apply_live_voice_turn_addon(system_instruction: str) -> str:
    if not getattr(settings, "gemini_live_append_turn_instructions", True):
        return system_instruction or ""
    s = (system_instruction or "").rstrip()
    add = _LIVE_VOICE_TURN_ADDENDUM.strip()
    if not s:
        return add
    return f"{s}\n\n{add}"
