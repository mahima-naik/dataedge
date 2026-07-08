"""Inbound WhatsApp → Dariaan (vernikaai) lead list."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from config import settings
from core.utils import _norm_phone_str


DARIAAN_ROLE = "vernikaai"


def wa_me_link(number_e164: str, prefill: str = "") -> str:
    """Build wa.me deep link for QR codes (digits only, no +)."""
    digits = "".join(c for c in (number_e164 or "") if c.isdigit())
    if not digits:
        return ""
    from urllib.parse import quote

    base = f"https://wa.me/{digits}"
    msg = (prefill or settings.dariaan_whatsapp_qr_message or "").strip()
    if msg:
        return f"{base}?text={quote(msg)}"
    return base


async def upsert_dariaan_lead_from_whatsapp(
    *,
    from_phone: str,
    profile_name: str = "",
    message_text: str = "",
    wa_message_id: str = "",
) -> tuple[int, bool]:
    """Insert or update a Dariaan lead from WhatsApp. Returns (lead_id, is_new)."""

    from core.storage import find_lead_by_phone, _get_conn

    norm = _norm_phone_str(from_phone)
    if not norm:
        raise ValueError(f"Invalid WhatsApp sender phone: {from_phone!r}")

    display_name = (profile_name or "").strip() or "WhatsApp Lead"
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    wa_meta = {
        "source": "whatsapp",
        "whatsapp_last_message": (message_text or "")[:2000],
        "whatsapp_last_message_id": wa_message_id or "",
        "whatsapp_last_at": now_iso,
    }

    existing = await find_lead_by_phone(DARIAAN_ROLE, norm)
    conn = _get_conn()

    if existing:
        lead_id = int(existing["id"])
        try:
            extra = json.loads(existing.get("extra") or "{}")
        except json.JSONDecodeError:
            extra = {}
        if not isinstance(extra, dict):
            extra = {}
        extra.update(wa_meta)
        name = (existing.get("name") or "").strip()
        if name.lower() in ("", "unknown", "whatsapp lead") and display_name:
            name = display_name
        conn.execute(
            """
            UPDATE leads SET
                name = ?,
                extra = ?,
                status = CASE WHEN status IN ('failed', 'not_interested') THEN 'pending' ELSE status END,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (name, json.dumps(extra, ensure_ascii=False), lead_id),
        )
        conn.commit()
        logger.info("WhatsApp lead updated id={} phone={}", lead_id, norm)
        return lead_id, False

    extra = dict(wa_meta)
    cur = conn.execute(
        """
        INSERT INTO leads (role, name, phone, email, company, details, extra, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            DARIAAN_ROLE,
            display_name,
            norm,
            "",
            "",
            (message_text or "")[:500],
            json.dumps(extra, ensure_ascii=False),
        ),
    )
    conn.commit()
    lead_id = int(cur.lastrowid)
    logger.info("WhatsApp new lead id={} phone={} name={!r}", lead_id, norm, display_name)
    return lead_id, True


async def process_dariaan_whatsapp_inbound(
    *,
    from_phone: str,
    profile_name: str = "",
    message_text: str = "",
    wa_message_id: str = "",
) -> dict[str, Any]:
    """Shared ingest: upsert lead, optional auto-reply, optional auto-dial."""
    if not settings.whatsapp_inbound_leads_enabled:
        return {"ignored": True, "reason": "WHATSAPP_INBOUND_LEADS_ENABLED=0"}

    lead_id, is_new = await upsert_dariaan_lead_from_whatsapp(
        from_phone=from_phone,
        profile_name=profile_name,
        message_text=message_text,
        wa_message_id=wa_message_id,
    )
    out: dict[str, Any] = {"lead_id": lead_id, "new": is_new}
    if is_new:
        await maybe_send_whatsapp_auto_reply(from_phone)
        out["auto_dial"] = await trigger_dariaan_auto_dial()
    return out


async def trigger_dariaan_auto_dial() -> dict[str, Any]:
    """Start Dariaan campaign worker if idle so new WhatsApp leads get called."""
    if not settings.whatsapp_auto_dial_dariaan:
        return {"started": False, "reason": "WHATSAPP_AUTO_DIAL_DARIAAN=0"}

    import asyncio

    from core.state import _CAMPAIGN_TASKS
    from core.storage import set_campaign_want_running
    from core.worker import _campaign_worker_role, _schedule_preflight

    role = DARIAAN_ROLE
    run = _CAMPAIGN_TASKS.get(role)
    if run and not run.done():
        return {"started": False, "reason": "campaign_already_running"}

    err = await _schedule_preflight(role)
    if err:
        logger.warning("WhatsApp auto-dial skipped: {}", err)
        return {"started": False, "reason": err}

    await set_campaign_want_running(role, True)
    _CAMPAIGN_TASKS[role] = asyncio.create_task(
        _campaign_worker_role(role),
        name=f"whatsapp-auto-dial-{role}",
    )
    logger.info("WhatsApp inbound → started Dariaan campaign for auto-dial")
    return {"started": True, "role": role}


async def maybe_send_whatsapp_auto_reply(to_phone: str) -> None:
    """Thank-you after new inbound — Meta Cloud API or whatsapp-web.js sidecar."""
    body = (
        "Thank you for contacting *Dariaan* (fashion & retail accelerator). "
        "Our team will reach out shortly. www.dariaan.in"
    )
    digits = "".join(c for c in (to_phone or "") if c.isdigit())
    if not digits:
        return

    if settings.whatsapp_proxy_enabled:
        import httpx

        headers: dict[str, str] = {}
        secret = (settings.whatsapp_proxy_secret or "").strip()
        if secret:
            headers["X-Proxy-Secret"] = secret
        base = (settings.whatsapp_proxy_url or "http://127.0.0.1:3001").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    f"{base}/send",
                    json={"to": digits, "text": body},
                    headers=headers,
                )
                if resp.status_code < 400:
                    return
                logger.warning("Proxy auto-reply failed: {} {}", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Proxy auto-reply error: {}", e)

    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return
    import httpx

    pid = settings.whatsapp_phone_number_id.strip()
    url = f"https://graph.facebook.com/v21.0/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": digits,
        "type": "text",
        "text": {"body": body},
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                json=payload,
            )
            if resp.status_code >= 400:
                logger.warning("WhatsApp auto-reply failed: {} {}", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("WhatsApp auto-reply error: {}", e)


async def _send_via_openwa(to_digits: str, text: str) -> dict[str, Any]:
    """Send via OpenWA API Gateway (replaces old whatsapp-proxy sidecar)."""
    if not settings.openwa_enabled:
        return {"sent": False, "error": "OPENWA_ENABLED=0"}
    api_url = settings.openwa_api_url.rstrip("/")
    session_id = settings.openwa_session_id.strip()
    api_key = settings.openwa_api_key.strip()
    if not session_id or not api_key:
        return {"sent": False, "error": "OPENWA_SESSION_ID or OPENWA_API_KEY not configured"}
    import httpx
    url = f"{api_url}/api/sessions/{session_id}/messages/send-text"
    chat_id = f"{to_digits}@c.us"
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                url,
                json={"chatId": chat_id, "text": text},
                headers={"X-API-Key": api_key},
            )
            if resp.status_code < 400:
                return {"sent": True, "to": to_digits, "via": "openwa", "status_code": resp.status_code}
            logger.warning("OpenWA send failed: {} {}", resp.status_code, (resp.text or "")[:200])
            return {"sent": False, "error": resp.text[:300], "via": "openwa", "status_code": resp.status_code}
    except Exception as e:
        logger.warning("OpenWA send error: {}", e)
        return {"sent": False, "error": str(e), "via": "openwa"}


async def _send_via_cloud_api(to_digits: str, text: str) -> dict[str, Any]:
    """Send via Meta WhatsApp Cloud API."""
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return {"sent": False, "error": "WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID not configured"}
    import httpx
    pid = settings.whatsapp_phone_number_id.strip()
    url = f"https://graph.facebook.com/v21.0/{pid}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_digits,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                json=payload,
            )
            if resp.status_code >= 400:
                err_text = resp.text[:500]
                logger.warning("Cloud API send failed: {} {}", resp.status_code, err_text)
                return {"sent": False, "error": err_text, "via": "cloud_api", "status_code": resp.status_code}
            logger.info("Cloud API message sent to {}", to_digits)
            return {"sent": True, "to": to_digits, "via": "cloud_api", "status_code": resp.status_code}
    except Exception as e:
        logger.warning("Cloud API send error: {}", e)
        return {"sent": False, "error": str(e), "via": "cloud_api"}


async def _send_image_openwa(to_digits: str, image_path: str, caption: str = "") -> dict[str, Any]:
    """Send an image via OpenWA send-image endpoint using base64."""
    if not settings.openwa_enabled:
        return {"sent": False, "error": "OPENWA_ENABLED=0"}
    api_url = settings.openwa_api_url.rstrip("/")
    session_id = settings.openwa_session_id.strip()
    api_key = settings.openwa_api_key.strip()
    if not session_id or not api_key:
        return {"sent": False, "error": "OPENWA_SESSION_ID or OPENWA_API_KEY not configured"}

    import base64 as _b64
    import os as _os
    import mimetypes as _mt
    try:
        with open(image_path, "rb") as f:
            raw = f.read()
        mime = _mt.guess_type(image_path)[0] or "image/jpeg"
        b64_str = _b64.b64encode(raw).decode()
    except Exception as e:
        return {"sent": False, "error": f"Failed to read image: {e}"}

    chat_id = f"{to_digits}@c.us"
    url = f"{api_url}/api/sessions/{session_id}/messages/send-image"
    payload = {"chatId": chat_id, "base64": b64_str, "mimetype": mime}
    if caption:
        payload["caption"] = caption

    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers={"X-API-Key": api_key})
            if resp.status_code < 400:
                return {"sent": True, "to": to_digits, "via": "openwa_image", "status_code": resp.status_code}
            logger.warning("OpenWA image send failed: {} {}", resp.status_code, (resp.text or "")[:200])
            return {"sent": False, "error": resp.text[:300], "via": "openwa_image", "status_code": resp.status_code}
    except Exception as e:
        logger.warning("OpenWA image send error: {}", e)
        return {"sent": False, "error": str(e), "via": "openwa_image"}


async def _send_document_openwa(to_digits: str, file_path: str, filename: str = "") -> dict[str, Any]:
    """Send a document (PDF) via OpenWA send-document endpoint using base64."""
    if not settings.openwa_enabled:
        return {"sent": False, "error": "OPENWA_ENABLED=0"}
    api_url = settings.openwa_api_url.rstrip("/")
    session_id = settings.openwa_session_id.strip()
    api_key = settings.openwa_api_key.strip()
    if not session_id or not api_key:
        return {"sent": False, "error": "OPENWA_SESSION_ID or OPENWA_API_KEY not configured"}

    import base64 as _b64
    import mimetypes as _mt
    try:
        with open(file_path, "rb") as f:
            raw = f.read()
        mime = _mt.guess_type(file_path)[0] or "application/pdf"
        b64_str = _b64.b64encode(raw).decode()
    except Exception as e:
        return {"sent": False, "error": f"Failed to read document: {e}"}

    fname = filename or file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    chat_id = f"{to_digits}@c.us"
    url = f"{api_url}/api/sessions/{session_id}/messages/send-document"
    payload = {"chatId": chat_id, "base64": b64_str, "mimetype": mime, "filename": fname}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers={"X-API-Key": api_key})
            if resp.status_code < 400:
                return {"sent": True, "to": to_digits, "via": "openwa_doc", "status_code": resp.status_code}
            logger.warning("OpenWA doc send failed: {} {}", resp.status_code, (resp.text or "")[:200])
            return {"sent": False, "error": resp.text[:300], "via": "openwa_doc", "status_code": resp.status_code}
    except Exception as e:
        logger.warning("OpenWA doc send error: {}", e)
        return {"sent": False, "error": str(e), "via": "openwa_doc"}


async def _send_video_openwa(to_digits: str, video_path: str, caption: str = "") -> dict[str, Any]:
    """Send a video via OpenWA send-video endpoint using base64.

    If the video is larger than WhatsApp Web's upload limit, it is automatically
    compressed using ffmpeg before sending.
    """
    if not settings.openwa_enabled:
        return {"sent": False, "error": "OPENWA_ENABLED=0"}
    api_url = settings.openwa_api_url.rstrip("/")
    session_id = settings.openwa_session_id.strip()
    api_key = settings.openwa_api_key.strip()
    if not session_id or not api_key:
        return {"sent": False, "error": "OPENWA_SESSION_ID or OPENWA_API_KEY not configured"}

    from services.video_compressor import compress_video_if_needed

    compressed_path: Optional[str] = None
    try:
        compressed_path = compress_video_if_needed(video_path)
        if not os.path.exists(compressed_path):
            return {"sent": False, "error": f"Video not found: {video_path}"}

        import base64 as _b64
        import mimetypes as _mt
        with open(compressed_path, "rb") as f:
            raw = f.read()
        mime = _mt.guess_type(compressed_path)[0] or "video/mp4"
        b64_str = _b64.b64encode(raw).decode()

        chat_id = f"{to_digits}@c.us"
        url = f"{api_url}/api/sessions/{session_id}/messages/send-video"
        payload: dict[str, Any] = {"chatId": chat_id, "base64": b64_str, "mimetype": mime}
        if caption:
            payload["caption"] = caption

        import httpx
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers={"X-API-Key": api_key})
            if resp.status_code < 400:
                return {"sent": True, "to": to_digits, "via": "openwa_video", "status_code": resp.status_code}
            logger.warning("OpenWA video send failed: {} {}", resp.status_code, (resp.text or "")[:200])
            return {"sent": False, "error": resp.text[:300], "via": "openwa_video", "status_code": resp.status_code}
    except Exception as e:
        logger.warning("OpenWA video send error: {}", e)
        return {"sent": False, "error": str(e), "via": "openwa_video"}
    finally:
        # Clean up compressed temp file only if it differs from the original.
        if compressed_path and compressed_path != video_path and os.path.exists(compressed_path):
            try:
                os.remove(compressed_path)
                logger.debug("Removed compressed video temp file: {}", compressed_path)
            except Exception as e:
                logger.warning("Failed to remove compressed video temp file: {}", e)


async def send_whatsapp_project_details(to_phone: str, summary: str = "", lead_name: str = "") -> dict[str, Any]:
    """Send project details via WhatsApp: video + text + multiple PDFs (configurable via env).

    Order: 1) Video with caption, 2) Text details, 3) PDF documents.
    Tries OpenWA first, falls back to Cloud API for text only.
    Legacy image/brochure settings are used as fallback when new video/doc paths are empty.
    """
    import asyncio as _aio
    import os as _os

    normalized = _norm_phone_str(to_phone)
    digits = "".join(c for c in normalized if c.isdigit())
    if not digits:
        return {"sent": False, "error": "invalid phone number"}

    greeting = settings.whatsapp_project_greeting_template.format(name=lead_name or "") if lead_name else ""
    if not greeting:
        greeting = f"Hi {lead_name}, " if lead_name else ""

    body = settings.whatsapp_project_details_body.strip()
    if not body:
        body = "Thank you for your interest. Please find the details below."
    if summary:
        body = f"*{summary}*\n\n---\n\n" + body

    results = []

    # 1) Send video via OpenWA (new primary media)
    video_path = settings.whatsapp_project_video_path
    if video_path and _os.path.exists(video_path):
        video_result = await _send_video_openwa(digits, video_path, caption=greeting)
        results.append(("video", video_result))
        if video_result.get("sent"):
            logger.info("Project video sent to {}", digits)
        await _aio.sleep(1.5)
    else:
        # Fallback to legacy image setting if no video is configured
        image_path = settings.whatsapp_project_image_path
        if image_path and _os.path.exists(image_path):
            img_result = await _send_image_openwa(digits, image_path, caption=greeting)
            results.append(("image", img_result))
            if img_result.get("sent"):
                logger.info("Project image sent to {}", digits)
            await _aio.sleep(1.5)
        else:
            logger.debug("No project video or image configured or found, skipping")

    # 2) Send text details via OpenWA or Cloud API
    full_text = f"{greeting}\n\n{body}" if greeting else body
    text_result = await _send_via_openwa(digits, full_text)
    if not text_result.get("sent"):
        text_result = await _send_via_cloud_api(digits, full_text)
    results.append(("text", text_result))
    if text_result.get("sent"):
        logger.info("Project details text sent to {}", digits)

    await _aio.sleep(1.5)

    # 3) Send multiple PDF documents (new primary documents)
    doc_paths = []
    if settings.whatsapp_project_doc_paths:
        for p in settings.whatsapp_project_doc_paths.split(","):
            p = p.strip()
            if p:
                doc_paths.append(p)

    # Fallback to legacy single brochure setting
    if not doc_paths:
        brochure_path = settings.whatsapp_project_brochure_path
        if brochure_path:
            doc_paths.append(brochure_path)

    for idx, doc_path in enumerate(doc_paths, start=1):
        if not _os.path.exists(doc_path):
            logger.debug("Document {} not found: {}", idx, doc_path)
            continue
        fname = doc_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        doc_result = await _send_document_openwa(digits, doc_path, filename=fname)
        results.append((f"document_{idx}", doc_result))
        if doc_result.get("sent"):
            logger.info("Document {} sent to {}", idx, digits)
        if idx < len(doc_paths):
            await _aio.sleep(1.5)

    # Return overall success
    any_sent = any(r.get("sent") for _, r in results)
    return {"sent": any_sent, "to": digits, "details": results}


async def send_whatsapp_text_message(to_phone: str, text: str) -> dict[str, Any]:
    """Send a free-form text message via WhatsApp.

    Tries OpenWA first, falls back to Meta Cloud API if configured.
    """
    normalized = _norm_phone_str(to_phone)
    digits = "".join(c for c in normalized if c.isdigit())
    if not digits or not text:
        return {"sent": False, "error": "invalid phone or empty text"}

    openwa_result = await _send_via_openwa(digits, text)
    if openwa_result.get("sent"):
        return openwa_result

    logger.warning("OpenWA send failed ({}), trying Cloud API fallback", openwa_result.get("error"))
    return await _send_via_cloud_api(digits, text)


def parse_meta_webhook_messages(body: dict) -> list[dict[str, Any]]:
    """Extract inbound user messages from Meta WhatsApp webhook JSON."""
    out: list[dict[str, Any]] = []
    if (body.get("object") or "") != "whatsapp_business_account":
        return out
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            if (change.get("field") or "") != "messages":
                continue
            value = change.get("value") or {}
            profiles = {
                str(c.get("wa_id", "")): (c.get("profile") or {}).get("name", "")
                for c in (value.get("contacts") or [])
            }
            for msg in value.get("messages") or []:
                if (msg.get("type") or "") != "text":
                    continue
                text_body = ((msg.get("text") or {}).get("body") or "").strip()
                from_id = str(msg.get("from") or "")
                out.append(
                    {
                        "from": from_id,
                        "profile_name": profiles.get(from_id, ""),
                        "text": text_body,
                        "message_id": str(msg.get("id") or ""),
                    }
                )
    return out
