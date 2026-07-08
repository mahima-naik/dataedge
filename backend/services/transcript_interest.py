"""Detect soft-positive sales interest from caller text (email/WhatsApp/send details/will check)."""

from __future__ import annotations

import json
import re
from typing import Iterable

# Firm rejection — never mark Interested
_NEGATIVE = re.compile(
    r"(?:"
    r"not\s+interested|no\s+interest|don'?t\s+call|do\s+not\s+call|stop\s+calling|"
    r"remove\s+(?:me|my)|take\s+me\s+off|wrong\s+number|galat\s+number|"
    r"never\s+call|already\s+have\s+(?:a\s+)?vendor"
    r")",
    re.I,
)

# Auto-attendant / carrier IVR — not a prospect
_IVR = re.compile(
    r"(?:"
    r"press\s+(?:one|two|three|\d)|hindi\s+ke\s+liye|for\s+english|english\s+press|"
    r"airtel|jio|vodafone|miss\s+call\s+seva|apni\s+pasand\s+ki\s+seva|"
    r"your\s+call\s+will\s+be\s+recorded|stay\s+on\s+the\s+line|"
    r"chhattisgarhi\s+mein|speed\s+up\s+airtel"
    r")",
    re.I,
)

# Soft interest — email, send details, will review, etc.
_POSITIVE = re.compile(
    r"(?:"
    r"send\s+(?:me|us|the|kar|dijiye|dijiyega|details|information|info|a\s+note|write.?up|brochure)|"
    r"(?:please\s+)?(?:share|bhej|bhejna|bhej\s+dijiye|mail\s+kar)\s+.*(?:detail|info|email|mail|whatsapp)|"
    r"(?:email|e-?mail|whatsapp|whats\s*app).{0,40}(?:send|share|bhej|kar\s+dijiye|pe\s+bhej)|"
    r"(?:send|share).{0,30}(?:email|e-?mail|whatsapp|whats\s*app|mail)|"
    r"whatsapp\s+(?:me\s+)?(?:the\s+)?(?:detail|info|information|brochure|course|pricing|quote|write.?up)|"
    r"(?:message|text|ping|contact)\s+(?:me\s+)?(?:on|via|through)\s+(?:whatsapp|whats\s*app)|"
    r"(?:send|share).{0,30}(?:through|via)\s+(?:whatsapp|whats\s*app)|"
    r"(?:provide|give|share).{0,20}(?:my\s+)?(?:email|e-?mail|mail\s+id)|"
    r"(?:requested|asked|wants?).{0,30}(?:email|whatsapp|details|information)|"
    r"information\s+via\s+(?:email|whatsapp)|preference\s+for.{0,20}(?:email|whatsapp)|"
    r"will\s+check|i'?ll\s+check|let\s+me\s+check|check\s+and\s+(?:get\s+back|revert)|"
    r"(?:our\s+)?people\s+will\s+decide|decide\s+on\s+that|"
    r"expressed\s+interest|(?:i\s+am|i'?m)\s+interested|"
    r"(?:okay|ok|theek|thik)\s*.{0,12}(?:send|bhej|mail)|"
    r"(?:demo|quotation|quote|pricing|brochure).{0,30}(?:send|email|share)|"
    r"note\s+write.?up|write.?up\s+on\s+that|"
    r"sales@|@(?:gmail|yahoo|outlook|hotmail|co\.in|com)\b|"
    r"call\s+(?:me\s+)?(?:back|after|later|tomorrow|on)|"
    r"(?:phone|ring|baat|callback)\s+(?:me\s+)?(?:after|later|tomorrow|on)|"
    r"(?:after|before|around)\s+\d{1,2}\s*(?:pm|am|bajey|baje)?|"
    r"kal\s+(?:call|phone|baat|karna|kariye)|"
    r"tomorrow\s+(?:call|phone)|"
    r"call\s+(?:karna|kariye|kar\s+lena)"
    r")",
    re.I,
)


def _iter_turns(transcript_text: str) -> Iterable[tuple[str, str]]:
    for line in (transcript_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = str(obj.get("role") or obj.get("type") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = str(obj.get("content") or obj.get("text") or obj.get("message") or "").strip()
        if content:
            yield role, content


def _iter_user_lines(transcript_text: str) -> Iterable[str]:
    for role, content in _iter_turns(transcript_text):
        if role == "user":
            yield content


_AFFIRMATIVE = re.compile(
    r"^(?:yes|yeah|yep|yup|ok(?:ay)?|sure|please|haan|haanji|ha|ji|theek|thik|"
    r"bilkul|send\s+it|go\s+ahead|bhej|kar\s+dijiye|mail\s+kar|interested)\b",
    re.I,
)

_ASK_SEND = re.compile(
    r"(?:send|share|bhej|mail|email|whatsapp).{0,40}(?:detail|info|information|email|mail|brochure)|"
    r"(?:can|shall|may)\s+i\s+send",
    re.I,
)


def caller_text_from_transcript(transcript_text: str) -> str:
    return " ".join(_iter_user_lines(transcript_text))


def _assistant_asked_send_user_agreed(transcript_text: str) -> bool:
    """e.g. assistant offers email → user says yes / okay / haan."""
    turns = list(_iter_turns(transcript_text))
    for i, (role, content) in enumerate(turns):
        if role != "assistant" or not _ASK_SEND.search(content):
            continue
        for j in range(i + 1, min(i + 4, len(turns))):
            r2, c2 = turns[j]
            if r2 == "user" and (_AFFIRMATIVE.search(c2) or _POSITIVE.search(c2)):
                return True
    return False


def soft_interest_in_text(*chunks: str | None) -> bool:
    """True when combined text shows send-details / email / will-review style interest."""
    blob = " ".join(str(c or "").strip() for c in chunks if c)
    if len(blob) < 8:
        return False
    if _NEGATIVE.search(blob):
        return False
    if _POSITIVE.search(blob):
        return True
    return False


def is_likely_ivr_or_no_prospect(transcript_text: str) -> bool:
    user = caller_text_from_transcript(transcript_text)
    if not user or len(user) < 12:
        return False
    if _IVR.search(user) and not _POSITIVE.search(user):
        return True
    return False


def infer_interest_from_transcript(transcript_text: str) -> bool:
    user = caller_text_from_transcript(transcript_text)
    if is_likely_ivr_or_no_prospect(transcript_text):
        return False
    if _assistant_asked_send_user_agreed(transcript_text):
        return True
    if not user or len(user) < 4:
        return False
    return soft_interest_in_text(user)


def apply_interest_disposition_override(
    analysis: dict,
    transcript_text: str | None = None,
) -> dict:
    """
    Upgrade generic ``Answered`` (or empty) to ``Interested`` when caller asked for
    email/WhatsApp/details or will review — matches Procucev sellers QA expectations.
    """
    out = dict(analysis or {})
    from services.call_analyzer import canonical_disposition

    canon = canonical_disposition(out.get("disposition"))
    if canon in ("Interested", "Not Interested", "Busy", "Wrong Number"):
        return out

    hit = False
    if transcript_text and infer_interest_from_transcript(transcript_text):
        hit = True
    if not hit:
        hit = soft_interest_in_text(
            out.get("summary"),
            out.get("next_steps"),
        )

    if hit:
        out["disposition"] = "Interested"
        out["outcome_from_transcript"] = True
        if not str(out.get("next_steps") or "").strip() or out.get("next_steps") == "N/A":
            out["next_steps"] = "Send requested details via email or WhatsApp and schedule follow-up."
    return out
