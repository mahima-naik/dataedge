"""Auto-send WhatsApp messages when lead is marked as Interested after a call.

This module is triggered from worker.py after call analysis completes with
disposition "Interested". It sends project details (image, text, brochure)
via OpenWA API Gateway with Meta Cloud API fallback.

All message attempts are logged to whatsapp_message_log table for tracking.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from loguru import logger

from config import settings


async def maybe_send_interested_whatsapp(
    lead_id: int,
    phone: str,
    role: str,
    analysis: dict,
) -> dict[str, Any]:
    """Trigger WhatsApp message when lead is marked Interested.

    This is the main entry point called from worker.py after disposition
    is determined to be "Interested". It:
    1. Checks if auto-send is enabled
    2. Validates phone number
    3. Sends project details via WhatsApp
    4. Logs the result to whatsapp_message_log table

    Args:
        lead_id: The lead's database ID
        phone: The lead's phone number (raw or normalized)
        role: The campaign role (e.g., "data_edge", "vernikaai")
        analysis: The call analysis dict with summary, disposition, etc.

    Returns:
        dict with keys: sent, lead_id, phone, details, error
    """
    from core.storage import log_whatsapp_message, update_whatsapp_message_status

    result: dict[str, Any] = {
        "sent": False,
        "lead_id": lead_id,
        "phone": phone,
        "role": role,
        "details": [],
        "error": None,
    }

    logger.info("maybe_send_interested_whatsapp called lead_id={} phone={!r} role={!r}", lead_id, phone, role)

    # Gate: feature must be enabled
    if not settings.whatsapp_auto_send_enabled:
        logger.warning("WhatsApp auto-send disabled (WHATSAPP_AUTO_SEND_ON_INTERESTED=0)")
        result["error"] = "WHATSAPP_AUTO_SEND_ON_INTERESTED=0"
        return result

    # Gate: OpenWA or Cloud API must be configured
    if not settings.openwa_enabled and not settings.whatsapp_access_token:
        logger.warning("WhatsApp auto-send: neither OPENWA_ENABLED nor WHATSAPP_ACCESS_TOKEN configured")
        result["error"] = "No WhatsApp provider configured"
        return result

    logger.info("WhatsApp auto-send gates passed lead_id={} openwa={} cloud={}", lead_id, settings.openwa_enabled, bool(settings.whatsapp_access_token))

    # Extract lead name and phone from DB record
    lead_name = ""
    try:
        from core.storage import get_lead
        lead = await get_lead(role, lead_id)
        if lead:
            lead_name = (lead.get("name") or "").strip()
            if lead_name.lower() in ("", "unknown"):
                lead_name = ""
            # Use DB phone as fallback when argument is empty/invalid
            if not phone or not phone.strip():
                phone = (lead.get("phone") or "").strip()
    except Exception as e:
        logger.debug("Could not fetch lead from DB: {}", e)

    # Normalize phone
    from core.utils import _norm_phone_str
    normalized = _norm_phone_str(phone)
    digits = "".join(c for c in normalized if c.isdigit()) if normalized else ""
    if not digits or len(digits) < 10:
        logger.warning("WhatsApp auto-send: invalid phone for lead {} (arg={!r})", lead_id, phone)
        result["error"] = f"Invalid phone: {phone!r}"
        return result

    # Fallback for manual calls (no lead row): use _callee_name from analysis
    if not lead_name:
        lead_name = (analysis.get("_callee_name") or "").strip()
        if lead_name.lower() in ("", "unknown"):
            lead_name = ""

    summary = (analysis.get("summary") or "").strip()

    # Log attempt as Pending
    log_id = await log_whatsapp_message(
        lead_id=lead_id,
        phone=digits,
        role=role,
        message_type="project_details",
        status="Pending",
        provider="openwa" if settings.openwa_enabled else "cloud_api",
        analysis_summary=summary[:500],
    )

    # Send with retry (1 retry after 5 seconds)
    send_result = await _send_with_retry(digits, summary, lead_name, max_retries=1)

    # Update log status
    final_status = "Sent" if send_result.get("sent") else "Failed"
    error_msg = send_result.get("error", "") if not send_result.get("sent") else ""

    await update_whatsapp_message_status(
        message_id=log_id,
        status=final_status,
        error=error_msg[:500] if error_msg else "",
    )

    result["sent"] = send_result.get("sent", False)
    result["details"] = send_result.get("details", [])
    result["error"] = error_msg if not send_result.get("sent") else None

    if result["sent"]:
        logger.info(
            "WhatsApp auto-send SUCCESS: lead_id={} phone={} via={}",
            lead_id, digits, send_result.get("via", "openwa"),
        )
    else:
        logger.warning(
            "WhatsApp auto-send FAILED: lead_id={} phone={} error={}",
            lead_id, digits, result.get("error"),
        )

    return result


async def _send_with_retry(
    digits: str,
    summary: str,
    lead_name: str,
    max_retries: int = 1,
) -> dict[str, Any]:
    """Send project details with retry logic."""
    from services.whatsapp_leads import send_whatsapp_project_details

    last_result: dict[str, Any] = {}
    for attempt in range(max_retries + 1):
        try:
            last_result = await send_whatsapp_project_details(
                to_phone=digits,
                summary=summary,
                lead_name=lead_name,
            )
            if last_result.get("sent"):
                last_result["via"] = "openwa" if settings.openwa_enabled else "cloud_api"
                return last_result

            logger.warning(
                "WhatsApp send attempt {}/{} failed: {}",
                attempt + 1, max_retries + 1, last_result.get("error"),
            )
        except Exception as e:
            logger.warning("WhatsApp send attempt {}/{} exception: {}", attempt + 1, max_retries + 1, e)
            last_result = {"sent": False, "error": str(e)}

        # Wait before retry (except on last attempt)
        if attempt < max_retries:
            await asyncio.sleep(5.0)

    return last_result
