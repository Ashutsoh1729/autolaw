"""Pydantic schemas for Document."""

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    matter_id: str
    filename: str
    original_type: str
    file_size_bytes: int = 0
    doc_type: str | None = None
    processing_status: str
    processing_error: str | None = None
    page_count: int | None = None
    uploaded_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class DocumentProcessResponse(BaseModel):
    document_id: str
    status: str
    message: str
    ocr_text_preview: str | None = None
