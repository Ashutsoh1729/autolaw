"""Document upload, storage, and listing service."""

import os
from typing import BinaryIO

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.document import Document
from app.models.matter import Matter
from app.schemas.document import DocumentResponse
from app.storage.local import storage_provider


def _infer_original_type(filename: str) -> str:
    """Infer the original document type from the file extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".pdf",):
        return "pdf"
    elif ext in (".txt",):
        return "txt"
    elif ext in (".eml", ".msg"):
        return "email"
    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"):
        return "image"
    return "pdf"  # default


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".eml", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


def validate_file(filename: str, file_size: int) -> tuple[bool, str]:
    """Validate a file's extension and size. Returns (is_valid, error_message)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File type '{ext}' is not supported. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if file_size > max_bytes:
        return False, f"File exceeds the maximum size of {settings.max_file_size_mb} MB"

    return True, ""


async def upload_document(
    db: AsyncSession,
    matter_id: str,
    filename: str,
    content: bytes,
) -> Document:
    """Upload a document: validate, store, and create the DB record."""
    file_size = len(content)

    # Validate
    valid, error = validate_file(filename, file_size)
    if not valid:
        raise ValueError(error)

    # Check matter exists
    matter_result = await db.execute(select(Matter).where(Matter.id == matter_id))
    matter = matter_result.scalar_one_or_none()
    if not matter:
        raise ValueError(f"Matter {matter_id} not found")

    # Check per-matter total limit
    current_usage = storage_provider.get_matter_usage_bytes(matter_id)
    max_total = settings.max_matter_total_mb * 1024 * 1024
    if current_usage + file_size > max_total:
        raise ValueError(
            f"Total storage for this matter would exceed {settings.max_matter_total_mb} MB limit"
        )

    # Check for duplicate filename
    existing_q = await db.execute(
        select(Document).where(
            Document.matter_id == matter_id,
            Document.filename == filename,
        )
    )
    if existing_q.scalar_one_or_none():
        raise ValueError(f"A document named '{filename}' already exists in this matter")

    # Store file
    original_type = _infer_original_type(filename)
    storage_path = await storage_provider.save(matter_id, filename, content)

    # Create DB record
    doc = Document(
        matter_id=matter_id,
        filename=filename,
        original_type=original_type,
        storage_path=storage_path,
        file_size_bytes=file_size,
        processing_status="pending",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


async def list_documents(
    db: AsyncSession, matter_id: str, skip: int = 0, limit: int = 100
) -> tuple[list[Document], int]:
    """List documents for a matter."""
    # Count
    count_q = select(func.count()).select_from(
        select(Document).where(Document.matter_id == matter_id).subquery()
    )
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    query = (
        select(Document)
        .where(Document.matter_id == matter_id)
        .order_by(Document.uploaded_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    docs = list(result.scalars().all())
    return docs, total


async def get_document(db: AsyncSession, doc_id: str) -> Document | None:
    """Get a single document by ID."""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()


def document_to_response(doc: Document) -> DocumentResponse:
    """Convert a Document ORM model to a Pydantic response."""
    return DocumentResponse(
        id=doc.id,
        matter_id=doc.matter_id,
        filename=doc.filename,
        original_type=doc.original_type,
        file_size_bytes=doc.file_size_bytes,
        doc_type=doc.doc_type,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
        page_count=doc.page_count,
        uploaded_at=doc.uploaded_at,
    )
