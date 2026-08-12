"""Resolve Vobiz auth + CLI per console role (env overrides stale DB for dedicated trunks)."""

from __future__ import annotations

from typing import Mapping, Optional, Tuple

from loguru import logger

from config import settings
from core.outbound_numbers import resolve_outbound_from_number
from core.state import normalize_console_role


def _data_edge_env_configured() -> bool:
    return bool(
        (settings.vobiz_data_edge_auth_id or "").strip()
        and (settings.vobiz_data_edge_auth_token or "").strip()
        and (settings.vobiz_data_edge_from_number or "").strip()
    )


def resolve_vobiz_credentials(
    role: str,
    vobiz_cfg: Optional[Mapping[str, object]] = None,
) -> Tuple[str, str, str, str]:
    """
    Return (auth_id, auth_token, from_number, public_url) for outbound dial.
    """
    r = normalize_console_role(role)
    vc = dict(vobiz_cfg or {})

    _env_url = (settings.vobiz_public_base_url or "").strip().rstrip("/")
    _role_url = str(vc.get("public_url") or "").strip().rstrip("/")

    # CRITICAL: If the role state has a Hostinger domain (.hstgr.cloud) but env
    # provides a direct URL, ALWAYS prefer the env URL.  Hostinger's reverse proxy
    # blocks WebSocket upgrades (101 Switching Protocols), causing calls to produce
    # silence or disconnect within seconds.
    if _role_url and "hstgr.cloud" in _role_url.lower():
        if _env_url and "hstgr.cloud" not in _env_url.lower():
            logger.debug(
                "resolve_vobiz_credentials: overriding role public_url {} with env {} "
                "(Hostinger proxy blocks WebSocket upgrades)",
                _role_url,
                _env_url,
            )
            _role_url = _env_url
    elif not _role_url:
        _role_url = _env_url

    public_url = _role_url or _env_url

    if r == "data_edge" and _data_edge_env_configured():
        return (
            settings.vobiz_data_edge_auth_id.strip(),
            settings.vobiz_data_edge_auth_token.strip(),
            settings.vobiz_data_edge_from_number.strip(),
            public_url,
        )

    # Dedicated role must NOT fall back to the global fallback account.
    if r == "data_edge":
        return "", "", "", public_url

    auth_id = str(vc.get("auth_id") or settings.vobiz_auth_id or "").strip()
    auth_token = str(vc.get("auth_token") or settings.vobiz_auth_token or "").strip()
    from_number = resolve_outbound_from_number(role, vc)
    return auth_id, auth_token, from_number, public_url
