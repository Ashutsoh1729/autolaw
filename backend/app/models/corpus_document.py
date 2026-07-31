"""CorpusDocument model — represents an ingested case law document."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Possible ingestion states for a corpus document.
CORPUS_DOCUMENT_STATUSES = ("pending", "ingesting", "ready", "failed")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CorpusDocument(Base):
    """A single case-law document ingested into the RAG corpus."""

    __tablename__ = "corpus_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_name: Mapped[str] = mapped_column(String(500), nullable=False)
    citation: Mapped[str] = mapped_column(String(255), nullable=False)
    court: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # R2 / storage object key of the original uploaded file.
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Model + dimension used to embed this document's chunks so reprocessing
    # can detect embedding-model mismatches.
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
