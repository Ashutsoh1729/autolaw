"""Timeline API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.event import TimelineFilterParams, TimelineResponse
from app.services.matter import get_matter
from app.services.timeline import get_timeline_events

router = APIRouter(prefix="/api/matters/{matter_id}/timeline", tags=["Timeline"])


@router.get("", response_model=TimelineResponse)
async def get_timeline_endpoint(
    matter_id: str,
    date_from: str | None = Query(None, description="Filter: start date (ISO 8601)"),
    date_to: str | None = Query(None, description="Filter: end date (ISO 8601)"),
    person: str | None = Query(None, description="Filter: person name"),
    search: str | None = Query(None, description="Full-text search in title/description"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
):
    """Get the chronological timeline of events for a matter."""
    # Verify matter exists
    matter = await get_matter(db, matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    filters = TimelineFilterParams(
        date_from=date_from,
        date_to=date_to,
        person=person,
        search=search,
    )

    events, total = await get_timeline_events(
        db, matter_id, filters=filters, skip=skip, limit=limit
    )

    return TimelineResponse(
        matter_id=matter_id,
        total_events=total,
        events=events,
        filters=filters,
    )
