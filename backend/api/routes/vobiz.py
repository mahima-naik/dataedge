"""Vobiz answer URL + media WebSocket."""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Request, Response, WebSocket
from loguru import logger

from config import settings
from core.state import (
    role_has_active_vobiz_call,
    _CAMPAIGN_DATA,
    _CAMPAIGN_TASKS,
    get_state,
    normalize_console_role,
    parse_manual_camp_role_suffix,
)
from core.storage import record_inbound_callback
from services.vobiz_bridge import build_answer_xml, handle_vobiz_ws_live

router = APIRouter(tags=["vobiz"])

# Inbound DID → role (last 10 digits). Vobiz Answer URL may pass any ?role=; To number wins.
_INBOUND_DID_ROLE: dict[str, str] = {
    "8065481138": "maruti",
    "8065481827": "data_edge",
    "8065480640": "vernikaai",
    "8065480856": "param_mahindra",
}


def _phone_last10(value: Optional[str]) -> str:
    if not value:
        return ""
    digits = "".join(c for c in str(value) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


async def _parse_vobiz_request(request: Optional[Request]) -> tuple[dict, str, Optional[str], Optional[str]]:
    """Return (raw_data, from_phone, to_phone, call_uuid)."""
    from_phone = "unknown"
    to_phone = None
    call_uuid = None
    raw_data: dict = {}
    if request is None:
        return raw_data, from_phone, to_phone, call_uuid
    try:
        qp = dict(request.query_params)
        ct = (request.headers.get("content-type") or "").lower()
        body_data: dict = {}
        if "application/x-www-form-urlencoded" in ct:
            form = await request.form()
            body_data = dict(form)
        elif "application/json" in ct:
            try:
                body_data = await request.json()
            except Exception:
                pass
        raw_data = {**qp, **body_data}
        from_phone = (
            body_data.get("From")
            or body_data.get("from")
            or qp.get("From")
            or qp.get("from")
            or "unknown"
        )
        to_phone = body_data.get("To") or body_data.get("to") or qp.get("To") or qp.get("to")
        call_uuid = body_data.get("CallUUID") or qp.get("CallUUID")
    except Exception as exc:
        logger.warning("Vobiz answer: inbound parse failed: {}", exc)
    return raw_data, from_phone, to_phone, call_uuid


def _resolve_inbound_role(query_role: Optional[str], to_phone: Optional[str]) -> str:
    """Map Vobiz Answer URL ?role= and called DID to the console sandbox role."""
    explicit = normalize_console_role(query_role) if query_role else None
    mapped = _INBOUND_DID_ROLE.get(_phone_last10(to_phone))
    if mapped:
        if explicit and explicit != mapped:
            logger.info(
                "Vobiz inbound DID {} remapped role {} → {}",
                to_phone,
                explicit,
                mapped,
            )
        return mapped
    return explicit or "sellers"


def _build_busy_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Reject reason="busy"/></Response>'
    )


async def _vobiz_answer_impl(
    camp_id: Optional[str] = None,
    role: Optional[str] = None,
    request: Optional[Request] = None,
) -> Response:
    is_inbound = bool(role) and not camp_id
    raw_data: dict = {}
    from_phone = "unknown"
    to_phone = None
    call_uuid = None
    if is_inbound and request is not None:
        raw_data, from_phone, to_phone, call_uuid = await _parse_vobiz_request(request)

    normalized_role = (
        _resolve_inbound_role(role, to_phone)
        if is_inbound
        else normalize_console_role(role) if role else None
    )

    is_busy = False
    if normalized_role:
        campaign_task = _CAMPAIGN_TASKS.get(normalized_role)
        if campaign_task and not campaign_task.done():
            is_busy = True
        if role_has_active_vobiz_call(normalized_role):
            is_busy = True

    if is_inbound and is_busy:
        try:
            await record_inbound_callback(
                normalized_role,
                from_phone,
                to_phone=to_phone,
                call_uuid=call_uuid,
                campaign_active=True,
                raw_start={"direction": "inbound", "busy_rejected": True, "raw": raw_data},
            )
        except Exception as exc:
            logger.warning("record_inbound_callback failed: {}", exc)

        return Response(content=_build_busy_xml(), media_type="application/xml")

    db_lead = None
    if camp_id and camp_id not in _CAMPAIGN_DATA:
        try:
            from core.storage import lead_row_by_call_id
            db_lead = await lead_row_by_call_id(camp_id)
        except Exception as e:
            logger.warning("Vobiz answer: failed to recover campaign lead from DB: {}", e)

    role_base = None
    if camp_id and (camp_id in _CAMPAIGN_DATA or db_lead):
        data = _CAMPAIGN_DATA[camp_id] if camp_id in _CAMPAIGN_DATA else db_lead
        camp_role = data.get("_role") or data.get("role")
        if camp_role:
            state = get_state(camp_role)
            role_base = state.get("vobiz", {}).get("public_url")
    elif normalized_role:
        try:
            state = get_state(normalized_role)
            role_base = state.get("vobiz", {}).get("public_url")
        except Exception:
            role_base = None

    dyn_base = None
    if request and not (settings.vobiz_stream_public_base_url or "").strip():
        req_host = request.headers.get("host") or request.url.netloc
        if req_host:
            proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
            dyn_base = f"{proto}://{req_host}"

    base = (dyn_base or role_base or settings.vobiz_public_base_url or "").rstrip("/")
    stream_base = (settings.vobiz_stream_public_base_url or "").strip().rstrip("/") or base
    wss_url = stream_base.replace("https://", "wss://").replace("http://", "wss://") + "/ws/vobiz"

    params = []
    agent_id = None
    if camp_id:
        params.append(f"camp_id={camp_id}")
        if camp_id in _CAMPAIGN_DATA or db_lead:
            data = _CAMPAIGN_DATA[camp_id] if camp_id in _CAMPAIGN_DATA else db_lead
            agent_id = data.get("_agent_id") or data.get("agent_id")
        elif camp_id.startswith("sandbox-"):
            parts = camp_id.split("-")
            if len(parts) >= 2:
                agent_id = parts[1]

    if agent_id:
        params.append(f"agent_id={agent_id}")

    # NOTE: We intentionally do NOT append ``manual_role=...`` to the WSS URL
    # even for manual calls.  Vobiz's XML parser fails to decode ``&amp;``
    # entities inside the <Stream> text node, so any URL containing ``&``
    # (even when properly XML-escaped) causes Vobiz to silently drop the WS
    # connection.  The role is already determinable on the WS handler side
    # because the camp_id starts with ``manual_{role}_...``.
    if not camp_id and normalized_role:
        params.append(f"inbound_role={normalized_role}")

    if params:
        wss_url += "?" + "&".join(params)

    if stream_base and (
        "trycloudflare.com" in stream_base
        or "trycloudflare.dev" in stream_base
        or "cfargotunnel.com" in stream_base
    ):
        logger.warning(
            "Vobiz <Stream> URL uses a Cloudflare quick-tunnel host ({}…). "
            "If calls disconnect with no audio, set VOBIZ_STREAM_PUBLIC_BASE_URL to your VPS "
            "http://IP:PORT (same FastAPI server).",
            stream_base.split("//")[-1][:48],
        )

    if request is not None:
        try:
            logger.info(
                "Vobiz answer: method={} qs={}",
                request.method, dict(request.query_params),
            )
        except Exception:
            pass

    logger.info(
        "Vobiz answer: camp={} inbound={} role={} to={} wss_url={}",
        camp_id,
        is_inbound,
        normalized_role,
        to_phone,
        wss_url,
    )
    return Response(
        content=build_answer_xml(wss_url, inbound=is_inbound),
        media_type="application/xml",
    )


@router.post("/vobiz/answer")
async def vobiz_answer_post(request: Request, camp_id: Optional[str] = None, role: Optional[str] = None):
    return await _vobiz_answer_impl(camp_id=camp_id, role=role, request=request)


@router.get("/vobiz/answer")
async def vobiz_answer_get(request: Request, camp_id: Optional[str] = None, role: Optional[str] = None):
    return await _vobiz_answer_impl(camp_id=camp_id, role=role, request=request)


@router.websocket("/ws/vobiz")
async def vobiz_ws_endpoint(
    websocket: WebSocket,
    camp_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    inbound_role: Optional[str] = None,
    manual_role: Optional[str] = None,
):
    logger.info(
        "Vobiz WS connect: camp_id={} agent_id={} inbound_role={} manual_role={}",
        camp_id, agent_id, inbound_role, manual_role,
    )
    await handle_vobiz_ws_live(
        websocket,
        camp_id=camp_id,
        agent_id=agent_id,
        inbound_role=inbound_role,
        manual_role=manual_role,
    )
