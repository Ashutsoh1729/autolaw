"""Pydantic schemas for the Research (RAG search + brief) module.

These schemas define the API contract consumed by the frontend (Group C).
Endpoint paths and response shapes must match the "Boundaries" section of
``docs/plan/pipeline/phase-2/phase-2-search-and-brief.md``.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# Status values used by the brief pipeline.
BRIEF_STATUS_VALUES = ("complete", "partial", "no_results", "generating")


class ResearchSearchRequest(BaseModel):
    """Request body for ``POST /api/matters/{id}/research/search``."""

    query: str = Field(..., min_length=1, max_length=2000, description="Search query text")
    query_type: str = Field(
        "auto",
        pattern="^(auto|keyword|semantic)$",
        description="'auto', 'keyword', or 'semantic'",
    )
    filters: dict | None = Field(
        default=None, description="{court, jurisdiction, year_from, year_to}"
    )
    top_k: int = Field(10, ge=1, le=50, description="Number of results to return")


class SearchResultItem(BaseModel):
    """A single reranked search result returned to the frontend."""

    chunk_id: str
    corpus_document_id: str
    text: str
    case_name: str = ""
    citation: str = ""
    court: str = ""
    year: int = 0
    relevance_score: float = Field(0.0, ge=0.0, le=1.0)


class ResearchSearchResponse(BaseModel):
    """Response for the search endpoint.

    ``status`` and ``message`` are optional fields used for graceful
    degradation (e.g. empty corpus) — they are a superset of the plan's
    contract and default to ``"ok"``/``None``.
    """

    results: list[SearchResultItem] = Field(default_factory=list)
    total_results: int = 0
    query_used: str = ""
    status: str = Field("ok", pattern="^(ok|no_results|error)$")
    message: str | None = None


class ResearchBriefRequest(BaseModel):
    """Request body for brief generation / regeneration endpoints.

    The body is optional (brief generation can run purely from the matter
    context). ``query`` is optional so the frontend may either let the
    pipeline formulate queries from the matter, or force a specific query.
    """

    query: str | None = Field(
        default=None, max_length=2000, description="Optional query to use instead of formulation"
    )
    regenerate: bool = False
    sections: list[str] | None = Field(
        default=None,
        description='Optional list of sections to include (e.g. ["summary", "precedents", "statutes"])',
    )


class BriefCitation(BaseModel):
    """A single source citation referenced by a brief section."""

    citation: str
    passage: str
    relevance_score: float = Field(0.0, ge=0.0, le=1.0)
    corpus_document_id: str


class BriefSection(BaseModel):
    """A named section of a research brief."""

    title: str
    content: str
    citations: list[BriefCitation] = Field(default_factory=list)


class ResearchBriefResponse(BaseModel):
    """A structured research brief produced by LLM synthesis."""

    id: str
    matter_id: str
    query: str
    created_at: datetime
    summary: str
    sections: list[BriefSection] = Field(default_factory=list)
    status: str = Field(
        "generating", pattern="^(complete|partial|no_results|generating)$"
    )


class ResearchStatusResponse(BaseModel):
    """Lightweight status response for the research pipeline."""

    brief_id: str | None = None
    status: str = Field(
        "not_generated",
        pattern="^(not_generated|generating|complete|partial|no_results|error)$",
    )
    brief: ResearchBriefResponse | None = None
