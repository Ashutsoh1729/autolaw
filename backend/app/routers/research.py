"""Research API routes — search + brief generation (Phase 2, Group B).

Endpoints (API contract consumed by Group C — see the plan's Boundaries):

- ``POST /api/matters/{matter_id}/research/search``
- ``GET  /api/matters/{matter_id}/research/brief``
- ``POST /api/matters/{matter_id}/research/brief``
- ``POST /api/matters/{matter_id}/research/brief/regenerate``
- ``GET  /api/matters/{matter_id}/research/status``

``EmbeddingService`` and ``get_vector_store()``/``SearchResult`` are imported
from Group A's modules (``app/services/embedding.py`` and
``app/services/vector_store.py`` — read-only). While Group A is developed in
parallel, a deterministic embedding service and an in-memory vector store with
the identical interface are used as fallbacks so this module works standalone.
"""

import inspect
import json
import logging
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.event import Event
from app.models.matter import Matter
from app.schemas.research import (
    ResearchBriefRequest,
    ResearchBriefResponse,
    ResearchSearchRequest,
    ResearchSearchResponse,
    ResearchStatusResponse,
    SearchResultItem,
)
from app.services.brief_generator import BriefGenerator
from app.services.query_formulator import QueryFormulator
from app.services.reranker import Reranker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/matters/{matter_id}/research", tags=["Research"])

# ---------------------------------------------------------------------------
# Group A imports (read-only) with fallbacks for parallel development.
# ---------------------------------------------------------------------------
_HAS_GROUP_A = False
try:
    from app.services.embedding import EmbeddingService as GroupAEmbeddingService  # type: ignore
    from app.services.vector_store import (  # type: ignore
        SearchResult,
        get_vector_store as _group_a_get_vector_store,
    )

    _HAS_GROUP_A = True
except ImportError:  # pragma: no cover - exercised before Group A merges
    from app.services.reranker import SearchResult


class EmbeddingUnavailableError(Exception):
    """Raised when the embedding service cannot produce a query vector."""


class VectorSearchUnavailableError(Exception):
    """Raised when the vector store is unreachable or empty-backed."""


class DeterministicEmbeddingService:
    """Fallback embedding service (stable hash-based vectors).

    Used only when Group A's ``EmbeddingService`` is not yet available. The
    vectors are deterministic so search behavior is reproducible in tests and
    during local development without an OpenRouter key.
    """

    def __init__(self, dimension: int = 8) -> None:
        self._dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for index, char in enumerate(text.encode("utf-8")):
            vector[index % self._dimension] += char / 255.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    def embed_dimension(self) -> int:
        return self._dimension


class InMemoryVectorStore:
    """Fallback vector store with the same interface as Group A's VectorStore.

    Supports metadata filtering by ``court``, ``jurisdiction``, ``year_from``
    and ``year_to``. ``seed()`` is a testing/development convenience.
    """

    def __init__(self, embedder: Any | None = None) -> None:
        self._embedder = embedder or DeterministicEmbeddingService()
        self._points: list[dict[str, Any]] = []

    def seed(
        self,
        results: list[SearchResult],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """Store known results (with deterministic embeddings) for tests/dev."""
        for i, result in enumerate(results):
            if embeddings and i < len(embeddings):
                embedding = embeddings[i]
            else:
                embedding = self._embedder.embed(result.text)
            self._points.append({"embedding": embedding, "result": result})

    def clear(self) -> None:
        self._points = []

    async def store_chunks(self, chunks: list[Any]) -> list[str]:
        """Interface-compatible stub (used by Group A's ingestion pipeline)."""
        ids: list[str] = []
        for chunk in chunks:
            text = getattr(chunk, "text", "")
            metadata = dict(getattr(chunk, "metadata", {}) or {})
            chunk_id = str(getattr(chunk, "id", None) or uuid.uuid4())
            corpus_document_id = str(
                getattr(chunk, "corpus_document_id", "") or metadata.get("corpus_document_id", "")
            )
            embedding = getattr(chunk, "embedding", None)
            if embedding is None:
                embedding = self._embedder.embed(text)
            self._points.append(
                {
                    "embedding": embedding,
                    "result": SearchResult(
                        chunk_id=chunk_id,
                        corpus_document_id=corpus_document_id,
                        text=text,
                        metadata=metadata,
                        score=0.0,
                    ),
                }
            )
            ids.append(chunk_id)
        return ids

    async def search(
        self,
        embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        filters = filters or {}
        scored: list[tuple[float, SearchResult]] = []
        for point in self._points:
            result = point["result"]
            if not self._matches(result, filters):
                continue
            similarity = self._cosine(embedding, point["embedding"])
            scored.append((similarity, result))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            SearchResult(
                chunk_id=result.chunk_id,
                corpus_document_id=result.corpus_document_id,
                text=result.text,
                metadata=result.metadata,
                score=similarity,
            )
            for similarity, result in scored[:top_k]
        ]

    async def delete_chunks(self, corpus_document_id: str) -> int:
        before = len(self._points)
        self._points = [
            p for p in self._points if p["result"].corpus_document_id != corpus_document_id
        ]
        return before - len(self._points)

    async def collection_info(self) -> dict:
        return {
            "total_points": len(self._points),
            "dimension": self._embedder.embed_dimension(),
        }

    @staticmethod
    def _matches(result: SearchResult, filters: dict) -> bool:
        metadata = result.metadata or {}
        court = filters.get("court")
        if court and str(metadata.get("court", "")).lower() != str(court).lower():
            return False
        jurisdiction = filters.get("jurisdiction")
        if jurisdiction and str(metadata.get("jurisdiction", "")).lower() != str(jurisdiction).lower():
            return False
        try:
            year = int(metadata.get("year", 0))
        except (TypeError, ValueError):
            year = 0
        year_from = filters.get("year_from")
        if year_from is not None and year < int(year_from):
            return False
        year_to = filters.get("year_to")
        if year_to is not None and year > int(year_to):
            return False
        return True

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))


# ---------------------------------------------------------------------------
# Shared pipeline instances (module-level singletons; injectable for tests).
# ---------------------------------------------------------------------------
embedding_service: Any = None
vector_store: Any = None
reranker = Reranker()
formulator = QueryFormulator()
brief_generator = BriefGenerator()


def get_embedding_service() -> Any:
    """Return the shared embedding service (Group A's, or the fallback)."""
    global embedding_service
    if embedding_service is None:
        embedding_service = _build_embedding_service()
    return embedding_service


def get_vector_store() -> Any:
    """Return the shared vector store (Group A's, or the fallback)."""
    global vector_store
    if vector_store is None:
        vector_store = _build_vector_store()
    return vector_store


def reset_services() -> None:
    """Reset shared service singletons (used by tests)."""
    global embedding_service, vector_store
    embedding_service = None
    vector_store = None


def _build_embedding_service() -> Any:
    if _HAS_GROUP_A:
        try:
            return GroupAEmbeddingService()
        except Exception as e:  # pragma: no cover - defensive
            logger.error("Failed to initialize Group A EmbeddingService: %s. Using fallback.", e)
    return DeterministicEmbeddingService()


def _build_vector_store() -> Any:
    if _HAS_GROUP_A:
        try:
            return _group_a_get_vector_store()
        except Exception as e:  # pragma: no cover - defensive
            logger.error("Failed to initialize Group A vector store: %s. Using fallback.", e)
    return InMemoryVectorStore()


async def _embed(text: str) -> list[float]:
    """Embed ``text`` via the shared service (handles sync and async impls)."""
    result = get_embedding_service().embed(text)
    if inspect.isawaitable(result):
        return await result
    return result


async def _search_pipeline(
    query: str, filters: dict | None, top_k: int = 5
) -> list[SearchResult]:
    """Embed → vector search (top 20 raw) → rerank (top-k). Logs latency."""
    import time

    started = time.perf_counter()
    try:
        embedding = await _embed(query)
    except Exception as e:
        logger.error("Embedding service unavailable: %s", e)
        raise EmbeddingUnavailableError(str(e)) from e

    try:
        raw = await get_vector_store().search(embedding, top_k=max(20, top_k), filters=filters)
    except Exception as e:
        logger.error("Vector store search failed for query %r: %s", query, e)
        raise VectorSearchUnavailableError(str(e)) from e

    logger.info("Vector search for %r returned %d raw results (%.1f ms).", query, len(raw),
                (time.perf_counter() - started) * 1000)
    reranked = await reranker.rerank(query, raw, top_k=top_k)
    logger.info("Rerank kept %d results for %r.", len(reranked), query)
    return reranked


async def _collect_passages(queries: list[str], filters: dict | None) -> list[SearchResult]:
    """Run the search pipeline for each query and merge the results."""
    passages: list[SearchResult] = []
    for query in queries:
        try:
            results = await _search_pipeline(query, filters, top_k=5)
        except VectorSearchUnavailableError as e:
            logger.warning("Skipping query %r (vector store unavailable): %s", query, e)
            continue
        passages.extend(results)
    return _dedupe(passages)


def _dedupe(passages: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for passage in passages:
        if passage.chunk_id not in seen:
            seen.add(passage.chunk_id)
            unique.append(passage)
    return unique


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_matter_or_404(db: AsyncSession, matter_id: str) -> Matter:
    result = await db.execute(select(Matter).where(Matter.id == matter_id))
    matter = result.scalar_one_or_none()
    if matter is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    return matter


def _matter_context(matter: Matter) -> dict[str, Any]:
    return {
        "matter_id": matter.id,
        "title": matter.title,
        "case_number": matter.case_number,
        "case_type": matter.case_type,
        "jurisdiction": matter.jurisdiction,
        "description": matter.description,
    }


async def _get_timeline_events(db: AsyncSession, matter_id: str) -> list[dict[str, Any]]:
    result = await db.execute(select(Event).where(Event.matter_id == matter_id))
    events = list(result.scalars().all())
    return [
        {
            "title": event.title,
            "description": event.description or "",
            "people": json.loads(event.people) if event.people else [],
            "date": event.date,
        }
        for event in events
    ]


def _to_result_item(result: SearchResult) -> SearchResultItem:
    metadata = result.metadata or {}
    try:
        year = int(metadata.get("year", 0))
    except (TypeError, ValueError):
        year = 0
    return SearchResultItem(
        chunk_id=result.chunk_id,
        corpus_document_id=result.corpus_document_id,
        text=result.text,
        case_name=metadata.get("case_name", ""),
        citation=metadata.get("citation", ""),
        court=metadata.get("court", ""),
        year=year,
        relevance_score=result.score,
    )


def _brief_body(data: ResearchBriefRequest | None) -> tuple[str | None, bool]:
    """Extract (query, force) from an optional brief request body."""
    if data is None:
        return None, False
    query = data.query.strip() if data.query else None
    return query, bool(data.regenerate)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/search", response_model=ResearchSearchResponse)
async def search_endpoint(
    matter_id: str,
    data: ResearchSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run semantic search over the case law corpus for a matter."""
    await _get_matter_or_404(db, matter_id)
    query_used = data.query
    try:
        results = await _search_pipeline(query_used, data.filters, data.top_k)
    except EmbeddingUnavailableError as e:
        logger.error("Search failed — embedding unavailable: %s", e)
        raise HTTPException(status_code=503, detail="Embedding service unavailable") from e
    except VectorSearchUnavailableError as e:
        logger.error("Search degraded — vector store unavailable: %s", e)
        return ResearchSearchResponse(
            results=[],
            total_results=0,
            query_used=query_used,
            status="no_results",
            message="Vector search is unavailable. The case law corpus may not be ingested yet.",
        )

    items = [_to_result_item(r) for r in results]
    return ResearchSearchResponse(
        results=items,
        total_results=len(items),
        query_used=query_used,
        status="ok" if items else "no_results",
    )


@router.get("/brief", response_model=ResearchStatusResponse)
async def get_brief_endpoint(matter_id: str, db: AsyncSession = Depends(get_db)):
    """Return the current cached brief for a matter, if one exists."""
    await _get_matter_or_404(db, matter_id)
    brief = brief_generator.get_brief(matter_id)
    if brief is None:
        return ResearchStatusResponse(brief_id=None, status="not_generated", brief=None)
    return ResearchStatusResponse(brief_id=brief.id, status=brief.status, brief=brief)


@router.post("/brief", response_model=ResearchBriefResponse)
async def create_brief_endpoint(
    matter_id: str,
    data: ResearchBriefRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Generate a research brief for a matter (query optional; else formulated)."""
    matter = await _get_matter_or_404(db, matter_id)
    matter_context = _matter_context(matter)
    timeline_events = await _get_timeline_events(db, matter_id)

    query, force = _brief_body(data)
    if query:
        queries = [query]
    else:
        queries = await formulator.formulate(matter_context, timeline_events)
        query = queries[0] if queries else ""

    try:
        passages = await _collect_passages(queries, filters=None)
    except EmbeddingUnavailableError as e:
        logger.error("Brief generation failed — embedding unavailable: %s", e)
        raise HTTPException(status_code=503, detail="Embedding service unavailable") from e

    if not passages:
        return await brief_generator.generate(query, [], matter_context)

    return await brief_generator.generate(query, passages, matter_context, force=force)


@router.post("/brief/regenerate", response_model=ResearchBriefResponse)
async def regenerate_brief_endpoint(
    matter_id: str,
    data: ResearchBriefRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Re-run brief generation, bypassing the cache (optional new query)."""
    matter = await _get_matter_or_404(db, matter_id)
    matter_context = _matter_context(matter)
    timeline_events = await _get_timeline_events(db, matter_id)

    query, _ = _brief_body(data)
    if query:
        queries = [query]
    else:
        queries = await formulator.formulate(matter_context, timeline_events)
        query = queries[0] if queries else ""

    try:
        passages = await _collect_passages(queries, filters=None)
    except EmbeddingUnavailableError as e:
        logger.error("Brief regeneration failed — embedding unavailable: %s", e)
        raise HTTPException(status_code=503, detail="Embedding service unavailable") from e

    current = brief_generator.get_brief(matter_id)
    brief_id = current.id if current else str(uuid.uuid4())
    return await brief_generator.regenerate(brief_id, query, passages, matter_context)


@router.get("/status", response_model=ResearchStatusResponse)
async def status_endpoint(matter_id: str, db: AsyncSession = Depends(get_db)):
    """Lightweight status of the research pipeline for a matter."""
    await _get_matter_or_404(db, matter_id)
    brief = brief_generator.get_brief(matter_id)
    if brief is None:
        return ResearchStatusResponse(brief_id=None, status="not_generated", brief=None)
    return ResearchStatusResponse(brief_id=brief.id, status=brief.status, brief=brief)
