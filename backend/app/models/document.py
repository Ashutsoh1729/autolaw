"""Document model — represents an uploaded file within a matter."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    matter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_type: Mapped[str] = mapped_column(
        Enum("pdf", "txt", "email", "image", name="doc_original_type"),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_type: Mapped[str | None] = mapped_column(
        Enum(
            "contract",
            "email",
            "police_report",
            "medical_record",
            "correspondence",
            "other",
            name="doc_type_enum",
        ),
        nullable=True,
    )
    processing_status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "uploading",
            "ocr_pending",
            "ocr_done",
            "classifying",
            "classified",
            "extracting",
            "extracted",
            "failed",
            name="processing_status_enum",
        ),
        default="pending",
        nullable=False,
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    matter = relationship("Matter", back_populates="documents")
    events = relationship("Event", back_populates="source_document")
