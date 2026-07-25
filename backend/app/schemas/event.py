"""Pydantic schemas for Event and Timeline."""

from datetime import datetime

from pydantic import BaseModel, Field


class EventResponse(BaseModel):
    id: str
    matter_id: str
    source_document_id: str
    source_chunk_index: int | None = None
    date: str
    date_precision: str = "exact"
    date_end: str | None = None
    title: str
    description: str | None = None
    people: list[str] = Field(default_factory=list)
    doc_reference: str | None = None
    confidence: float = 1.0
    dedup_group: str | None = None
    source_filename: str | None = None


class TimelineFilterParams(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    person: str | None = None
    doc_type: str | None = None
    search: str | None = None


class TimelineResponse(BaseModel):
    matter_id: str
    total_events: int
    events: list[EventResponse]
    filters: TimelineFilterParams = Field(default_factory=TimelineFilterParams)
