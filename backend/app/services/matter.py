"""Matter CRUD service."""

import uuid
from datetime import datetime, timezone

from app.config import settings

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.matter import Matter
from app.models.document import Document
from app.schemas.matter import MatterCreate, MatterUpdate, MatterResponse


async def create_matter(db: AsyncSession, data: MatterCreate) -> Matter:
    """Create a new legal matter."""
    unique_email = f"{uuid.uuid4().hex[:8]}@{settings.email_domain}"
    matter = Matter(
        title=data.title,
        case_number=data.case_number,
        case_type=data.case_type,
        jurisdiction=data.jurisdiction,
        description=data.description,
        email_address=unique_email,
    )
    db.add(matter)
    await db.flush()
    await db.refresh(matter)
    return matter


async def get_matter(db: AsyncSession, matter_id: str) -> Matter | None:
    """Get a matter by ID."""
    result = await db.execute(select(Matter).where(Matter.id == matter_id))
    return result.scalar_one_or_none()


async def list_matters(
    db: AsyncSession, search: str | None = None, status: str | None = None, skip: int = 0, limit: int = 50
) -> tuple[list[Matter], int]:
    """List matters with optional search/filter."""
    query = select(Matter)

    if status:
        query = query.where(Matter.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Matter.title.ilike(pattern) | Matter.case_number.ilike(pattern)
        )

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    query = query.order_by(Matter.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    matters = list(result.scalars().all())
    return matters, total


async def update_matter(db: AsyncSession, matter_id: str, data: MatterUpdate) -> Matter | None:
    """Update a matter's fields."""
    matter = await get_matter(db, matter_id)
    if not matter:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(matter, key, value)
    matter.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(matter)
    return matter


async def delete_matter(db: AsyncSession, matter_id: str) -> bool:
    """Delete a matter and its files."""
    matter = await get_matter(db, matter_id)
    if not matter:
        return False
    await db.delete(matter)
    await db.flush()
    return True


def _matter_to_response(matter: Matter, doc_count: int = 0, processed_count: int = 0) -> MatterResponse:
    return MatterResponse(
        id=matter.id,
        title=matter.title,
        case_number=matter.case_number,
        case_type=matter.case_type,
        jurisdiction=matter.jurisdiction,
        description=matter.description,
        status=matter.status,
        email_address=matter.email_address,
        created_at=matter.created_at,
        updated_at=matter.updated_at,
        document_count=doc_count,
        processed_count=processed_count,
    )


async def get_matter_response(db: AsyncSession, matter: Matter) -> MatterResponse:
    """Build a MatterResponse with computed counts."""
    # Count documents
    doc_count_q = select(func.count()).select_from(
        select(Document).where(Document.matter_id == matter.id).subquery()
    )
    doc_result = await db.execute(doc_count_q)
    doc_count = doc_result.scalar() or 0

    # Count processed (done statuses)
    processed_q = select(func.count()).select_from(
        select(Document)
        .where(Document.matter_id == matter.id, Document.processing_status.in_(["extracted", "failed"]))
        .subquery()
    )
    proc_result = await db.execute(processed_q)
    processed_count = proc_result.scalar() or 0

    return _matter_to_response(matter, doc_count, processed_count)
