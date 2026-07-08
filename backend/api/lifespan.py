"""Application lifespan (DB init, shutdown)."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from config import FRONTEND_DIR, settings
from core.state import _CAMPAIGN_TASKS, init_state
from core.storage import (
    close_db,
    init_db,
    roles_with_campaign_run_wanted,
    set_campaign_want_running,
)
from services.vobiz_bridge import close_vobiz_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    logger.info("Starting bridge server…")
    data_root = (os.environ.get("VERN_DATA_DIR") or "").strip()
    if data_root:
        data_dir = os.path.abspath(data_root)
    else:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    init_db(data_dir)
    init_state()

    # Per-role sandbox: refresh packaged prompt/RAG and coerce cross-role greetings.
    try:
        from core.role_sandbox import sync_all_role_sandboxes_on_startup

        sync_all_role_sandboxes_on_startup()
    except Exception as exc:
        logger.warning("Role sandbox startup sync skipped: {}", exc)

    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — AI will fail")
    if not settings.vobiz_public_base_url:
        logger.warning("VOBIZ_PUBLIC_BASE_URL not set — Vobiz cannot reach this host")

    fe_index = FRONTEND_DIR / "index.html"
    if fe_index.is_file():
        logger.info(
            "Operator UI: http://127.0.0.1:{}/  (file {})",
            settings.port,
            fe_index,
        )
    else:
        logger.error(
            "Frontend index missing at {} — GET / will show a stub. "
            "Keep a sibling ``frontend/`` next to ``backend/`` (or rebuild Docker).",
            fe_index,
        )
    logger.info("OpenAPI / Swagger: http://127.0.0.1:{}/docs", settings.port)

    try:
        from core.state import get_lead_counts as _gcd
        from core.worker import (
            _campaign_worker_role,
            _schedule_preflight,
            release_orphaned_dialing_leads,
        )

        from core.storage import is_campaign_globally_paused

        if await is_campaign_globally_paused():
            logger.info("Global campaign pause is active — outbound dialers will not auto-resume.")
            resume_roles = []
        else:
            resume_roles = await roles_with_campaign_run_wanted()
        for r_role in resume_roles:
            ct = _gcd(r_role)
            if int(ct.get("pending", 0) or 0) <= 0 and int(ct.get("dialing", 0) or 0) <= 0:
                await set_campaign_want_running(r_role, False)
                continue
            why = await _schedule_preflight(r_role)
            if why:
                logger.warning("Campaign runner resume deferred role={}: {}", r_role, why)
                try:
                    from core.campaign_hours import is_campaign_quiet_hours

                    if is_campaign_quiet_hours():
                        await set_campaign_want_running(r_role, False)
                        await release_orphaned_dialing_leads(
                            r_role,
                            error="Campaign stopped: outside calling hours (9:30 AM – 8:30 PM IST).",
                        )
                except Exception:
                    pass
                continue
            existing = _CAMPAIGN_TASKS.get(r_role)
            if existing and not existing.done():
                continue
            _CAMPAIGN_TASKS[r_role] = asyncio.create_task(_campaign_worker_role(r_role))
            logger.info(
                "Resumed outbound dialer role={} (operator had Start before last restart)",
                r_role,
            )
    except Exception as exc:
        logger.warning("Campaign runner auto-resume skipped: {}", exc)

    sip_bridge = None
    if os.getenv("SIP_BRIDGE_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        try:
            from services.sip_bridge.server import SIPBridgeServer
            sip_bridge = SIPBridgeServer()
            await sip_bridge.start()
        except Exception as exc:
            logger.warning("SIP Bridge failed to start: {}", exc)

    logger.info("Bridge ready on {}:{}", settings.host, settings.port)
    yield

    for role, task in list(_CAMPAIGN_TASKS.items()):
        if task and not task.done():
            task.cancel()
            logger.info("Cancelled task for {}", role)
    if sip_bridge:
        await sip_bridge.stop()
    await close_vobiz_client()
    close_db()
    logger.info("Shutdown complete")
