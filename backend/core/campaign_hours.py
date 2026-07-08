"""Hard block for outbound campaign dialing outside allowed local hours (default IST)."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from config import settings
from services.callback_time import zoneinfo_safe


def _parse_hhmm(raw: str, default_h: int, default_m: int) -> time:
    s = (raw or "").strip()
    if not s:
        return time(default_h, default_m)
    parts = s.split(":")
    if len(parts) != 2:
        return time(default_h, default_m)
    try:
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("out of range")
        return time(h, m)
    except ValueError:
        return time(default_h, default_m)


def campaign_quiet_start() -> time:
    """First minute of the blocked window (inclusive), e.g. 20:30."""
    return _parse_hhmm(settings.campaign_quiet_start, 20, 30)


def campaign_quiet_end() -> time:
    """Last blocked minute ends when clock reaches this time (exclusive), e.g. 09:30."""
    return _parse_hhmm(settings.campaign_quiet_end, 9, 30)


def _now_in_tz() -> datetime:
    tz = zoneinfo_safe(settings.transcript_callback_tz)
    return datetime.now(tz)


def is_campaign_quiet_hours(now: datetime | None = None) -> bool:
    """True when outbound campaign dialing must not run (overnight window by default)."""
    if not settings.campaign_quiet_hours_enabled:
        return False
    tz = zoneinfo_safe(settings.transcript_callback_tz)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    t = now.time()
    start = campaign_quiet_start()
    end = campaign_quiet_end()
    if start > end:
        return t >= start or t < end
    return start <= t < end


def _fmt_time(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def quiet_hours_block_message() -> str:
    """Human-readable reason returned from preflight / API."""
    tz = (settings.transcript_callback_tz or "Asia/Kolkata").strip()
    qs = _fmt_time(campaign_quiet_start())
    qe = _fmt_time(campaign_quiet_end())
    return (
        f"Campaigns are blocked during quiet hours ({qs}–{qe} {tz}). "
        f"Outbound calling is allowed {qe}–{qs} only."
    )


def get_campaign_hours_status(now: datetime | None = None) -> dict[str, Any]:
    """Snapshot for dashboard / start-button gating."""
    tz_name = (settings.transcript_callback_tz or "Asia/Kolkata").strip()
    qs = campaign_quiet_start()
    qe = campaign_quiet_end()
    enabled = bool(settings.campaign_quiet_hours_enabled)
    in_quiet = is_campaign_quiet_hours(now) if enabled else False
    now_local = (now or _now_in_tz())
    if now_local.tzinfo:
        now_local = now_local.astimezone(zoneinfo_safe(tz_name))
    return {
        "enabled": enabled,
        "in_quiet_hours": in_quiet,
        "tz": tz_name,
        "quiet_start": _fmt_time(qs),
        "quiet_end": _fmt_time(qe),
        "allowed_start": _fmt_time(qe),
        "allowed_end": _fmt_time(qs),
        "local_time": now_local.strftime("%H:%M"),
        "block_message": quiet_hours_block_message() if in_quiet else "",
    }
