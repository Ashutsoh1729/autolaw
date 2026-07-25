"""Pydantic schemas for Matter."""

from datetime import datetime

from pydantic import BaseModel, Field


class MatterCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Case title (required)")
    case_number: str | None = Field(None, max_length=100)
    case_type: str | None = Field(None, max_length=50)
    jurisdiction: str | None = Field(None, max_length=255)
    description: str | None = Field(None)


class MatterUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    case_number: str | None = None
    case_type: str | None = None
    jurisdiction: str | None = None
    description: str | None = None
    status: str | None = Field(None, pattern="^(active|archived)$")


class MatterResponse(BaseModel):
    id: str
    title: str
    case_number: str | None = None
    case_type: str | None = None
    jurisdiction: str | None = None
    description: str | None = None
    status: str
    email_address: str | None = None
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    processed_count: int = 0


class MatterListResponse(BaseModel):
    matters: list[MatterResponse]
    total: int
