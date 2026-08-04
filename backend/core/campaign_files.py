"""Campaign file management — tracks uploaded lead files and their campaign status."""

from __future__ import annotations

from loguru import logger
from core import storage as lead_storage
from core.state import _CAMPAIGN_TASKS


async def list_files(role: str) -> list[dict]:
    """Return all campaign files for a role, syncing status with actual worker state."""
    files = await lead_storage.get_campaign_files(role)
    for f in files:
        if f.get("status") == "running":
            task = _CAMPAIGN_TASKS.get(role)
            if not task or task.done():
                await lead_storage.update_campaign_file_status(f["id"], "paused")
                f["status"] = "paused"
    return files


async def set_active(role: str, file_id: int) -> dict:
    """Set a file as the active campaign file. Stops any running campaign first."""
    import asyncio
    task = _CAMPAIGN_TASKS.get(role)
    campaign_running = task and not task.done()

    if campaign_running:
        await lead_storage.set_campaign_want_running(role, False)
        task.cancel()
        _CAMPAIGN_TASKS[role] = None
        from core.worker import release_orphaned_dialing_leads
        await release_orphaned_dialing_leads(role)

    await lead_storage.set_active_campaign_file(role, file_id)

    return {
        "status": "ok",
        "was_running": campaign_running,
        "campaign_stopped": campaign_running,
        "active_file_id": file_id,
    }


async def start_file_campaign(role: str, file_id: int) -> dict:
    """Start the campaign for a specific file."""
    import asyncio
    from core.worker import _campaign_worker_role, _schedule_preflight

    task = _CAMPAIGN_TASKS.get(role)
    if task and not task.done():
        return {"status": "already_running", "active": True}

    await lead_storage.set_active_campaign_file(role, file_id)
    await lead_storage.update_campaign_file_status(file_id, "running")

    err = await _schedule_preflight(role)
    if err:
        return {"status": "error", "error": err}

    await lead_storage.set_campaign_globally_paused(False)
    await lead_storage.set_campaign_want_running(role, True)
    _CAMPAIGN_TASKS[role] = asyncio.create_task(_campaign_worker_role(role))

    return {"status": "started", "active": True, "file_id": file_id}


async def stop_file_campaign(role: str) -> dict:
    """Stop the campaign for the current role."""
    task = _CAMPAIGN_TASKS.get(role)
    if not task or task.done():
        return {"status": "already_stopped", "active": False}

    await lead_storage.set_campaign_want_running(role, False)
    await lead_storage.set_campaign_globally_paused(True)
    task.cancel()
    _CAMPAIGN_TASKS[role] = None
    from core.worker import release_orphaned_dialing_leads
    await release_orphaned_dialing_leads(role)

    active = await lead_storage.get_active_campaign_file(role)
    if active:
        await lead_storage.update_campaign_file_status(active["id"], "paused")

    return {"status": "stopped", "active": False}


async def resume_file_campaign(role: str) -> dict:
    """Resume a paused campaign for the active file."""
    import asyncio
    from core.worker import _campaign_worker_role, _schedule_preflight

    task = _CAMPAIGN_TASKS.get(role)
    if task and not task.done():
        return {"status": "already_running", "active": True}

    active = await lead_storage.get_active_campaign_file(role)
    if not active:
        return {"status": "error", "error": "No active file selected"}

    await lead_storage.update_campaign_file_status(active["id"], "running")

    err = await _schedule_preflight(role)
    if err:
        return {"status": "error", "error": err}

    await lead_storage.set_campaign_globally_paused(False)
    await lead_storage.set_campaign_want_running(role, True)
    _CAMPAIGN_TASKS[role] = asyncio.create_task(_campaign_worker_role(role))

    return {"status": "started", "active": True, "file_id": active["id"]}
