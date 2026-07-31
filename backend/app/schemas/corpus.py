"""Pydantic schemas for corpus documents, chunks, and ingestion reports."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CorpusDocumentCreate(BaseModel):
    """Metadata required to create / ingest a corpus document."""

    case_name: str = Field(..., min_length=1, description="Full case name, e.g. 'Marbury v. Madison'")
    citation: str = Field(..., min_length=1, description="Legal citation, e.g. '5 U.S. 137'")
    court: str = Field(..., min_length=1, description="Court name, e.g. 'Supreme Court of the United States'")
    jurisdiction: str = Field(..., min_length=1, description="Jurisdiction, e.g. 'federal' or 'California'")
    year: int = Field(..., ge=1000, le=2100, description="Year of decision")
    url: str | None = Field(default=None, description="Optional source URL")
    summary: str | None = Field(default=None, description="Optional short summary")


class CorpusDocumentResponse(CorpusDocumentCreate):
    """A corpus document as returned by the API (create fields + DB state)."""

    id: str
    storage_path: str | None = Field(default=None, description="R2 / storage object key of the original file")
    embedding_model: str | None = Field(default=None, description="Embedding model used for this document's chunks")
    embedding_dimension: int | None = Field(default=None, description="Embedding dimension of this document's chunks")
    status: str = Field(..., description="pending | ingesting | ready | failed")
    created_at: datetime
    updated_at: datetime


class CorpusChunkSchema(BaseModel):
    """A single text chunk with citation metadata and optional embedding."""

    id: str | None = Field(default=None, description="Chunk/point ID; assigned by the VectorStore when None")
    corpus_document_id: str
    chunk_index: int
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = Field(default=None)


class IngestionReport(BaseModel):
    """Summary of a corpus ingestion run."""

    documents_ingested: int
    chunks_created: int
    elapsed_seconds: float
