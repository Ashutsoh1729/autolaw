"""Timeline service — builds structured timeline from extracted events."""

import json

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.document import Document
from app.schemas.event import EventResponse, TimelineFilterParams


async def get_timeline_events(
    db: AsyncSession,
    matter_id: str,
    filters: TimelineFilterParams | None = None,
    skip: int = 0,
    limit: int = 500,
) -> tuple[list[EventResponse], int]:
    """Retrieve events for a matter, sorted chronologically, with optional filters."""
    query = (
        select(Event)
        .where(Event.matter_id == matter_id)
    )

    # Apply filters
    if filters:
        if filters.date_from:
            query = query.where(Event.date >= filters.date_from)
        if filters.date_to:
            query = query.where(Event.date <= filters.date_to)
        if filters.person:
            query = query.where(Event.people.ilike(f"%{filters.person}%"))
        if filters.search:
            pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    Event.title.ilike(pattern),
                    Event.description.ilike(pattern),
                )
            )

    # Count before pagination
    count_q = select(Event.id).where(Event.matter_id == matter_id)
    if filters:
        if filters.date_from:
            count_q = count_q.where(Event.date >= filters.date_from)
        if filters.date_to:
            count_q = count_q.where(Event.date <= filters.date_to)
        if filters.person:
            count_q = count_q.where(Event.people.ilike(f"%{filters.person}%"))
        if filters.search:
            pattern = f"%{filters.search}%"
            count_q = count_q.where(
                or_(
                    Event.title.ilike(pattern),
                    Event.description.ilike(pattern),
                )
            )
    from sqlalchemy import func
    total_q = select(func.count()).select_from(count_q.subquery())
    total_result = await db.execute(total_q)
    total = total_result.scalar() or 0

    # Fetch with ordering
    query = query.order_by(Event.date).offset(skip).limit(limit)
    result = await db.execute(query)
    event_models = list(result.scalars().all())

    # Fetch document filenames for source references
    doc_ids = list(set(e.source_document_id for e in event_models if e.source_document_id))
    doc_map: dict[str, str] = {}
    if doc_ids:
        doc_result = await db.execute(
            select(Document.id, Document.filename).where(Document.id.in_(doc_ids))
        )
        for row in doc_result.all():
            doc_map[str(row.id)] = row.filename  # type: ignore[attr-defined]

    # Convert to response schemas
    events = [
        EventResponse(
            id=e.id,
            matter_id=e.matter_id,
            source_document_id=e.source_document_id,
            source_chunk_index=e.source_chunk_index,
            date=e.date,
            date_precision=e.date_precision,
            date_end=e.date_end,
            title=e.title,
            description=e.description,
            people=json.loads(e.people) if e.people else [],
            doc_reference=e.doc_reference,
            confidence=e.confidence,
            dedup_group=e.dedup_group,
            source_filename=doc_map.get(e.source_document_id, ""),
        )
        for e in event_models
    ]

    return events, total
