"""Event model — extracted chronological events from documents."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    matter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False
    )
    source_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    source_chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Date handling
    date: Mapped[str] = mapped_column(String(50), nullable=False)  # ISO 8601 or partial
    date_precision: Mapped[str] = mapped_column(
        Enum("exact", "month", "year", "range", name="date_precision_enum"),
        default="exact",
        nullable=False,
    )
    date_end: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Event content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    people: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON-serialized list
    doc_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # Deduplication
    dedup_group: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    matter = relationship("Matter", back_populates="events")
    source_document = relationship("Document", back_populates="events")
