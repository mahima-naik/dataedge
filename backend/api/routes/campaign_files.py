"""Campaign file management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from loguru import logger

router = APIRouter(prefix="/api/campaign/files", tags=["campaign-files"])


def _campaign_role(request: Request) -> str:
    from core.auth import console_role_from_request
    return console_role_from_request(request, default="data_edge")


@router.get("")
async def list_files(request: Request):
    """List all uploaded campaign files for the current role."""
    role = _campaign_role(request)
    from core.campaign_files import list_files
    files = await list_files(role)
    return {"status": "ok", "files": files}


@router.get("/active")
async def get_active_file(request: Request):
    """Get the currently active campaign file."""
    role = _campaign_role(request)
    from core import storage as lead_storage
    active = await lead_storage.get_active_campaign_file(role)
    return {"status": "ok", "active_file": active}


class SetActiveBody(BaseModel):
    file_id: int = Field(..., description="ID of the file to set as active")


@router.post("/active")
async def set_active_file(body: SetActiveBody, request: Request):
    """Set a file as the active campaign file. Stops any running campaign first."""
    role = _campaign_role(request)
    from core.campaign_files import set_active
    result = await set_active(role, body.file_id)
    return result


class StartFileBody(BaseModel):
    file_id: int = Field(..., description="ID of the file to start campaign on")


@router.post("/start")
async def start_file_campaign(body: StartFileBody, request: Request):
    """Start the campaign for a specific file."""
    role = _campaign_role(request)
    from core.campaign_files import start_file_campaign
    result = await start_file_campaign(role, body.file_id)
    return result


@router.post("/stop")
async def stop_file_campaign(request: Request):
    """Stop the currently running campaign."""
    role = _campaign_role(request)
    from core.campaign_files import stop_file_campaign
    result = await stop_file_campaign(role)
    return result


@router.post("/resume")
async def resume_file_campaign(request: Request):
    """Resume a paused campaign for the active file."""
    role = _campaign_role(request)
    from core.campaign_files import resume_file_campaign
    result = await resume_file_campaign(role)
    return result


class UpdateStatusBody(BaseModel):
    status: str = Field(..., description="New status: not_started, running, paused, completed")


@router.put("/{file_id}/status")
async def update_file_status(file_id: int, body: UpdateStatusBody, request: Request):
    """Update the status of a campaign file."""
    from core import storage as lead_storage
    await lead_storage.update_campaign_file_status(file_id, body.status)
    return {"status": "ok", "file_id": file_id, "new_status": body.status}


@router.delete("/{file_id}")
async def delete_file(file_id: int, request: Request):
    """Delete a campaign file record (does not delete leads, just unlinks them)."""
    from core import storage as lead_storage
    await lead_storage.delete_campaign_file(file_id)
    return {"status": "ok", "deleted": file_id}
