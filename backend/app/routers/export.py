"""Export API routes — timeline to Word/PDF."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.matter import get_matter
from app.services.timeline import get_timeline_events
from app.services.export import export_to_docx, export_to_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/matters/{matter_id}/export", tags=["Export"])


@router.get("")
async def export_timeline_endpoint(
    matter_id: str,
    format: str = Query("docx", pattern="^(docx|pdf)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export the timeline to Word (.docx) or PDF."""
    matter = await get_matter(db, matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    events, _ = await get_timeline_events(db, matter_id)

    if not events:
        raise HTTPException(
            status_code=404,
            detail="No timeline events found for this matter. Process documents first.",
        )

    if format == "docx":
        content = await export_to_docx(matter.title, events)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="timeline_{matter_id}.docx"'},
        )
    elif format == "pdf":
        content = await export_to_pdf(matter.title, events)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="timeline_{matter_id}.pdf"'},
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'docx' or 'pdf'.")
