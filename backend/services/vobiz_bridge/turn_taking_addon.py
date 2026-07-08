"""Optional system-instruction appendix for Gemini Live duplex / interruption behavior."""

from __future__ import annotations

from config import settings

_LIVE_VOICE_TURN_ADDENDUM = """

[REALTIME PHONE INTERACTION — TURN-TAKING]
This is a live voice call over the phone — not a monologue podcast.
Speak in SHORT segments; default to ONE clear sentence per turn unless the callee explicitly asks you to elaborate.
If the callee starts speaking, overlaps you, responds, or clears their throat mid-thought → STOP YOUR AUDIO immediately — yield fully and LISTEN until they finish.
Do NOT continue reasoning aloud over them or "talk through" silence.
Avoid long unsolicited monologues, lists, or repeated disclaimers unless the callee requests detail.
"""


def apply_live_voice_turn_addon(system_instruction: str) -> str:
    if not getattr(settings, "gemini_live_append_turn_instructions", True):
        return system_instruction or ""
    s = (system_instruction or "").rstrip()
    add = _LIVE_VOICE_TURN_ADDENDUM.strip()
    if not s:
        return add
    return f"{s}\n\n{add}"
