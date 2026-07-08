"""Interested Leads Feedback Manager API.

Endpoints:
- GET    /api/leads-feedback               — list with search, filter, sort, pagination
- POST   /api/leads-feedback               — create a new feedback entry
- PATCH  /api/leads-feedback/{row_id}      — update an existing entry
- DELETE /api/leads-feedback/{row_id}      — delete an entry
- GET    /api/leads-feedback/export        — export all (or filtered) records as CSV
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from core.storage import (
    add_feedback,
    delete_feedback,
    export_all_feedback,
    get_feedback,
    list_feedback,
    update_feedback,
)


router = APIRouter(prefix="/api/leads-feedback", tags=["leads-feedback"])


VALID_STATUSES = {"Interested", "Not Interested", "Callback", "No Answer", "Others"}


class FeedbackCreate(BaseModel):
    name: str
    contact_number: str
    lead_status: str
    custom_status: str = ""
    feedback_notes: str = ""


class FeedbackUpdate(BaseModel):
    name: Optional[str] = None
    contact_number: Optional[str] = None
    lead_status: Optional[str] = None
    custom_status: Optional[str] = None
    feedback_notes: Optional[str] = None


@router.get("")
async def list_feedback_entries(
    request: Request,
    search: str = Query("", description="Search by name or contact number"),
    status: str = Query("", alias="status", description="Filter by lead status"),
    sort_by: str = Query("created_at", description="Sort column"),
    sort_dir: str = Query("DESC", description="Sort direction: ASC or DESC"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    result = await list_feedback(
        search=search,
        status_filter=status,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return result


@router.post("")
async def create_feedback_entry(payload: FeedbackCreate, request: Request):
    name = (payload.name or "").strip()
    contact_number = (payload.contact_number or "").strip()
    lead_status = (payload.lead_status or "").strip()
    custom_status = (payload.custom_status or "").strip()
    feedback_notes = (payload.feedback_notes or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if not contact_number:
        raise HTTPException(status_code=400, detail="Contact Number is required.")
    if not lead_status:
        raise HTTPException(status_code=400, detail="Lead Status is required.")
    if lead_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid Lead Status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    row_id = await add_feedback(
        name=name,
        contact_number=contact_number,
        lead_status=lead_status,
        custom_status=custom_status,
        feedback_notes=feedback_notes,
    )
    logger.info(f"Created feedback entry id={row_id} name={name!r} status={lead_status!r}")
    row = await get_feedback(row_id)
    return {"status": "ok", "id": row_id, "item": row}


@router.patch("/{row_id}")
async def update_feedback_entry(row_id: int, payload: FeedbackUpdate):
    existing = await get_feedback(row_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Feedback entry not found.")

    name = payload.name.strip() if isinstance(payload.name, str) else None
    contact_number = payload.contact_number.strip() if isinstance(payload.contact_number, str) else None
    lead_status = payload.lead_status.strip() if isinstance(payload.lead_status, str) else None
    custom_status = payload.custom_status.strip() if isinstance(payload.custom_status, str) else None
    feedback_notes = payload.feedback_notes.strip() if isinstance(payload.feedback_notes, str) else None

    if name is not None and not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    if contact_number is not None and not contact_number:
        raise HTTPException(status_code=400, detail="Contact Number cannot be empty.")
    if lead_status is not None and lead_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid Lead Status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    ok = await update_feedback(
        row_id=row_id,
        name=name,
        contact_number=contact_number,
        lead_status=lead_status,
        custom_status=custom_status,
        feedback_notes=feedback_notes,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    row = await get_feedback(row_id)
    logger.info(f"Updated feedback entry id={row_id}")
    return {"status": "ok", "id": row_id, "item": row}


@router.delete("/{row_id}")
async def delete_feedback_entry(row_id: int):
    ok = await delete_feedback(row_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Feedback entry not found.")
    logger.info(f"Deleted feedback entry id={row_id}")
    return {"status": "ok", "id": row_id}


@router.get("/export")
async def export_feedback_csv(
    request: Request,
    search: str = Query("", description="Search filter"),
    status: str = Query("", alias="status", description="Status filter"),
):
    """Export feedback records as CSV. If search/status filters are provided, exports only matching records."""
    if search or status:
        result = await list_feedback(
            search=search,
            status_filter=status,
            sort_by="created_at",
            sort_dir="DESC",
            page=1,
            page_size=100000,
        )
        records = result["items"]
    else:
        records = await export_all_feedback()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Contact Number", "Lead Status", "Custom Status", "Feedback / Notes", "Date Created", "Last Updated"])
    for r in records:
        writer.writerow([
            r.get("name", ""),
            r.get("contact_number", ""),
            r.get("lead_status", ""),
            r.get("custom_status", ""),
            r.get("feedback_notes", ""),
            r.get("created_at", ""),
            r.get("updated_at", ""),
        ])

    output.seek(0)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"interested_leads_feedback_{now_str}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
