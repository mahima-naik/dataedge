"""Detect genuine course/program interest from caller text.

Per the Interested Lead Classification policy, weak signals alone (brochure,
demo, WhatsApp details, callback, "will check", non-committal replies) must NOT
mark a lead Interested.  Only conversations that clearly demonstrate genuine
interest in a DataEdge course/program qualify.
"""

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

# Weak signals — NOT sufficient on their own to mark Interested.  Require a
# genuine course/program interest signal elsewhere in the conversation.
_WEAK_SIGNAL = re.compile(
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
    r"will\s+let\s+you\s+know|let\s+you\s+know\s+later|"
    r"(?:our\s+)?people\s+will\s+decide|decide\s+on\s+that|"
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

# Genuine interest in a course/program/career path — this is what qualifies a
# lead as Interested.  Requires an explicit, non-committal-free signal that the
# caller is seriously pursuing or exploring a DataEdge program.
_GENUINE_INTEREST = re.compile(
    r"(?:"
    r"(?:i(?:'m|'am| am)?|we)\s+(?:am|are\s+)?(?:really|very|quite|definitely)?\s*interested\s+in\s+(?:the\s+|this\s+|that\s+|your\s+)?(?:course|program|training|diploma|data|analytics|ai|artificial\s+intelligence|career)|"
    r"\b(?:i|we)\s+(?:want|wants?)\s+to\s+(?:learn|pursue|join|do|study|take|enroll|enrol|explore|switch\s+to)\s+(?:in\s+|into\s+|the\s+|this\s+|that\s+)?(?:data|analytics|ai|artificial\s+intelligence|python|sql|course|program|training|diploma|career)|"
    r"\b(?:i(?:'m|'am| am)?|we)\s+(?:am|are\s+)?looking\s+for\s+(?:a\s+|an\s+)?(?:career|course|program|training)|"
    r"\bcareer\s+(?:change|switch|goal|path|transition|growth|progress)|"
    r"\b(?:this|that|the)\s+(?:course|program|training)\s+(?:is|sounds|seems|looks)\s+(?:relevant|good|interesting|perfect|right|useful|fitting|suits\s+me)|"
    r"\b(?:course|program|training)\s+(?:fits|matches|suits)\s+(?:me|my\s+(?:need|requirement|goal|profile))|"
    r"\bwants?\s+to\s+(?:learn|pursue|join|study)\s+(?:data|analytics|ai|course|program)|"
    r"\b(?:mujhe|hum)\s+(?:yeh|is|that)\s+(?:course|program)\s+(?:achha|accha|chahiye|pasand|relevant|seekhna\s+hai)|"
    r"\b(?:main|hum)\s+(?:data|ai|analytics)\s+(?:seekhna|sikhna|sikna)\s+(?:chahata|chahti|chahte)|"
    r"\b(?:i|we)\s+want\s+to\s+know\s+more\s+about\s+(?:the\s+|this\s+|that\s+)?(?:course|program|training|curriculum|data|ai)|"
    r"\b(?:about|of)\s+(?:the\s+)?(?:curriculum|syllabus|duration|structure)\b|"
    r"\binterested\s+(?:in|to)|"
    r"\bexpress(?:ed)?\s+(?:interest|an\s+interest)\b|"
    r"\b(?:learn|study|pursue)\s+(?:data|analytics|ai|artificial\s+intelligence|python|sql|course|program|training|diploma)\b"
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


def caller_text_from_transcript(transcript_text: str) -> str:
    return " ".join(_iter_user_lines(transcript_text))


def soft_interest_in_text(*chunks: str | None) -> bool:
    """True only when text shows genuine course/program interest (not just weak signals)."""
    blob = " ".join(str(c or "").strip() for c in chunks if c)
    if len(blob) < 8:
        return False
    if _NEGATIVE.search(blob):
        return False
    if _GENUINE_INTEREST.search(blob):
        return True
    return False


def is_likely_ivr_or_no_prospect(transcript_text: str) -> bool:
    user = caller_text_from_transcript(transcript_text)
    if not user or len(user) < 12:
        return False
    if _IVR.search(user) and not _GENUINE_INTEREST.search(user):
        return True
    return False


def infer_interest_from_transcript(transcript_text: str) -> bool:
    """True only when the caller demonstrates genuine course/program interest.

    Weak signals (brochure / demo / WhatsApp / callback / "will check") alone
    never qualify.  An explicit genuine-interest statement is required.
    """
    user = caller_text_from_transcript(transcript_text)
    if is_likely_ivr_or_no_prospect(transcript_text):
        return False
    if not user or len(user) < 4:
        return False
    if _NEGATIVE.search(user):
        return False
    return bool(_GENUINE_INTEREST.search(user))


def apply_interest_disposition_override(
    analysis: dict,
    transcript_text: str | None = None,
) -> dict:
    """
    Upgrade generic ``Answered`` (or empty) to ``Interested`` ONLY when the
    conversation clearly demonstrates genuine interest in a course/program.

    Weak signals (email/WhatsApp/details/demo/callback/"will check") on their
    own do NOT qualify — per the Interested Lead Classification policy.
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
            out["next_steps"] = "Follow up on the caller's genuine course interest and schedule a conversation."
    return out
