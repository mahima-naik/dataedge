"""Vobiz REST dial, answer XML, and stream start metadata."""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx
from loguru import logger

from xml.sax.saxutils import escape

from .constants import VOBIZ_CONTENT_TYPE, VOBIZ_SR

_vobiz_httpx_client: Optional[httpx.AsyncClient] = None


def _get_vobiz_client() -> httpx.AsyncClient:
    global _vobiz_httpx_client
    if _vobiz_httpx_client is None:
        _vobiz_httpx_client = httpx.AsyncClient(timeout=30.0)
    return _vobiz_httpx_client


async def close_vobiz_client() -> None:
    global _vobiz_httpx_client
    if _vobiz_httpx_client is not None:
        await _vobiz_httpx_client.aclose()
        _vobiz_httpx_client = None


def extract_vobiz_start_numbers(start: dict) -> tuple[str, str]:
    """Best-effort caller/callee numbers from Vobiz ``start`` JSON."""
    from_num, to_num = "", ""
    for k in (
        "From", "from", "callerId", "CallerId", "caller_id", "Caller",
        "caller", "remoteParty", "remoteIdentity", "fromNumber", "FromNumber",
        "CallerNumber", "callerNumber", "sipFrom", "SipFrom",
    ):
        v = start.get(k)
        if v is not None and str(v).strip():
            from_num = str(v).strip()
            break
    for k in (
        "To", "to", "called", "Called", "dialed", "Dialed", "toNumber", "ToNumber",
        "sipTo", "SipTo", "destination",
    ):
        v = start.get(k)
        if v is not None and str(v).strip():
            to_num = str(v).strip()
            break
    return from_num, to_num


def build_answer_xml(wss_stream_url: str, inbound: bool = False) -> str:
    del inbound  # routing is encoded in the WSS query string
    # ``&`` in query strings MUST be escaped in XML text — bare ``&manual_role`` breaks parsers and Vobiz never connects WS.
    # NOTE: audioTrack attribute removed - Vobiz docs state it should NOT be used with bidirectional="true"
    safe_url = escape(wss_stream_url, entities={'"': "&quot;", "'": "&apos;"})
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        '<Stream '
        'bidirectional="true" '
        'keepCallAlive="true" '
        f'contentType="{VOBIZ_CONTENT_TYPE};rate={VOBIZ_SR}" '
        'streamTimeout="3600">'
        f'{safe_url}'
        '</Stream>'
        '</Response>'
    )


class VobizCallError(RuntimeError):
    def __init__(self, status: int, payload: dict[str, Any], message: Optional[str] = None):
        self.status = int(status)
        self.payload = payload or {}
        self.message = (message or self._derive_message()).strip()
        super().__init__(self.message)

    def _derive_message(self) -> str:
        p = self.payload or {}
        for key in ("error", "message", "detail", "reason", "raw"):
            v = p.get(key)
            if v:
                return str(v)
        return f"Vobiz HTTP {self.status}"

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "message": self.message, "payload": self.payload}


async def make_vobiz_call(
    *,
    to: str,
    from_: str,
    answer_url: str,
    auth_id: str,
    auth_token: str,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"
    headers = {
        "X-Auth-ID": auth_id,
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "from": from_,
        "to": to,
        "answer_url": answer_url,
        "answer_method": "POST",
    }
    if extra:
        body.update(extra)

    client = _get_vobiz_client()
    logger.info(f"Vobiz Request Body: {body}")
    r = await client.post(url, json=body, headers=headers)
    try:
        data: dict[str, Any] = r.json()
    except Exception:
        data = {"raw": r.text}
    data["_http_status"] = r.status_code
    logger.info("Vobiz make_call {} -> HTTP {} {}", to, r.status_code, data)
    if r.status_code >= 400:
        raise VobizCallError(r.status_code, data)
    return data
