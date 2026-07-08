"""Parse deferred recall times emitted by transcript QA (e.g. \"call me at 5 pm\")."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger


def zoneinfo_safe(name: str) -> ZoneInfo:
    try:
        return ZoneInfo((name or "UTC").strip() or "UTC")
    except Exception:
        logger.warning(f"Invalid TRANSCRIPT_CALLBACK_TZ={name!r}; falling back to UTC")
        return ZoneInfo("UTC")


def parse_requested_callback_iso_to_utc_epoch(
    raw: Any,
    default_tz_name: str,
) -> float | None:
    """Return UTC epoch seconds for an ISO-ish string from the LLM, or None."""

    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("null", "none", "n/a"):
        return None

    tz = zoneinfo_safe(default_tz_name)

    normalized = s
    if normalized.endswith("z") or normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    normalized = normalized.replace(" ", "T", 1) if " " in normalized and "T" not in normalized.upper()[:12] else normalized

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            # Some models omit the T separator
            dt = datetime.fromisoformat(s.replace(" ", "T"))
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)

    utc = dt.astimezone(timezone.utc)
    return utc.timestamp()


def annotate_analysis_callback_epoch(
    analysis: dict[str, Any],
    *,
    tz_name: str,
) -> None:
    """Set ``analysis['callback_reminder_epoch']`` from ``requested_callback_datetime_iso``."""

    epoch = parse_requested_callback_iso_to_utc_epoch(
        analysis.get("requested_callback_datetime_iso"),
        tz_name,
    )
    if epoch is None:
        analysis.pop("callback_reminder_epoch", None)
    else:
        analysis["callback_reminder_epoch"] = epoch
