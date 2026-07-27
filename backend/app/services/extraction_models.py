"""Pydantic models for structured LLM event extraction output."""

from pydantic import BaseModel, Field


class ExtractedEvent(BaseModel):
    """A single chronological event extracted from a legal document."""

    date: str = Field(description="ISO 8601 date or partial date as written in the document")
    date_precision: str = Field(
        default="exact",
        pattern=r"^(exact|month|year|range)$",
        description="How precise the date is",
    )
    date_end: str | None = Field(default=None, description="End date for date ranges")
    title: str = Field(description="Short event title (max 100 chars)")
    description: str | None = Field(default=None, description="Detailed description of what happened")
    people: list[str] = Field(default_factory=list, description="Full names of people involved")
    doc_reference: str | None = Field(default=None, description="Page, paragraph, or section reference")
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence score 0.0–1.0"
    )


class EventExtractionResult(BaseModel):
    """Container for all events extracted from a single text chunk."""

    events: list[ExtractedEvent] = Field(
        default_factory=list, description="All events found in the chunk"
    )
