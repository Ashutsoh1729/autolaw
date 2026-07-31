"""Vector store abstraction for the RAG pipeline.

Defines the :class:`VectorStore` interface — the contract consumed by
Group B (search + brief) — plus a Qdrant implementation and a settings-
driven factory (:func:`get_vector_store`).

Importing search code (Group B) should depend only on the abstract
``VectorStore`` interface and the :class:`SearchResult` dataclass so the
backing store can be swapped (pgvector / ChromaDB) without API changes.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.schemas.corpus import CorpusChunkSchema

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = "corpus_chunks"

# Payload keys reserved by the vector store (everything else in the payload
# is treated as searchable metadata).
RESERVED_PAYLOAD_KEYS = {"text", "corpus_document_id", "chunk_index"}


@dataclass
class SearchResult:
    """A single vector search hit with metadata and similarity score."""

    chunk_id: str
    corpus_document_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class VectorStore(ABC):
    """Abstract interface for vector database operations."""

    @abstractmethod
    async def store_chunks(self, chunks: list[CorpusChunkSchema]) -> list[str]:
        """Persist chunks (with embeddings) and return their assigned IDs."""

    @abstractmethod
    async def search(
        self,
        embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Return the top-k chunks nearest to ``embedding``.

        ``filters`` narrows results by payload field values, e.g.
        ``{"court": "Supreme Court of the United States", "year": 1803}``.
        Results are ordered by descending similarity score.
        """

    @abstractmethod
    async def delete_chunks(self, corpus_document_id: str) -> int:
        """Delete all chunks belonging to a document; return count deleted."""

    @abstractmethod
    async def collection_info(self) -> dict[str, Any]:
        """Return collection stats, e.g. ``{"total_points": N, "dimension": D}``."""


class QdrantVectorStore(VectorStore):
    """Qdrant-backed implementation of :class:`VectorStore`.

    The Qdrant client is injectable so tests can use
    ``AsyncQdrantClient(location=":memory:")`` for hermetic runs.
    """

    def __init__(
        self,
        url: str | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        dimension: int | None = None,
        client: Any | None = None,
    ) -> None:
        self.url = url or settings.qdrant_url
        self.collection_name = collection_name
        self.dimension = dimension or settings.embedding_dimension
        if client is not None:
            self._client = client
        else:
            from qdrant_client import AsyncQdrantClient

            self._client = AsyncQdrantClient(url=self.url)

    # ── Collection setup ───────────────────────────────────────────────────

    async def ensure_collection(self) -> None:
        """Create the collection with cosine distance if it doesn't exist."""
        try:
            exists = await self._client.collection_exists(self.collection_name)
        except Exception:
            logger.exception(
                "Could not reach Qdrant at %s; is the docker-compose service running?",
                self.url,
            )
            raise
        if not exists:
            from qdrant_client.http import models as qdrant

            logger.info(
                "Creating Qdrant collection '%s' (dimension=%d, cosine)",
                self.collection_name,
                self.dimension,
            )
            await self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qdrant.VectorParams(
                    size=self.dimension, distance=qdrant.Distance.COSINE
                ),
            )

    # ── VectorStore interface ──────────────────────────────────────────────

    async def store_chunks(self, chunks: list[CorpusChunkSchema]) -> list[str]:
        if not chunks:
            return []
        await self.ensure_collection()
        from qdrant_client.http import models as qdrant

        points = []
        ids: list[str] = []
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(
                    f"Chunk {chunk.id or chunk.chunk_index} has no embedding; "
                    "embed before storing"
                )
            if len(chunk.embedding) != self.dimension:
                raise ValueError(
                    f"Chunk {chunk.id or chunk.chunk_index} embedding dimension "
                    f"{len(chunk.embedding)} does not match collection dimension "
                    f"{self.dimension}"
                )
            point_id = chunk.id or str(uuid.uuid4())
            ids.append(point_id)
            points.append(
                qdrant.PointStruct(
                    id=point_id,
                    vector=chunk.embedding,
                    payload={
                        "text": chunk.text,
                        "corpus_document_id": chunk.corpus_document_id,
                        "chunk_index": chunk.chunk_index,
                        **chunk.metadata,
                    },
                )
            )
        await self._client.upsert(
            collection_name=self.collection_name, points=points, wait=True
        )
        return ids

    async def search(
        self,
        embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        await self.ensure_collection()
        from qdrant_client.http import models as qdrant

        query_filter = self._build_filter(filters)
        response = await self._client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        results: list[SearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            metadata = {
                k: v for k, v in payload.items() if k not in RESERVED_PAYLOAD_KEYS
            }
            results.append(
                SearchResult(
                    chunk_id=str(point.id),
                    corpus_document_id=str(payload.get("corpus_document_id", "")),
                    text=str(payload.get("text", "")),
                    metadata=metadata,
                    score=float(point.score),
                )
            )
        return results

    async def delete_chunks(self, corpus_document_id: str) -> int:
        """Scroll matching points and delete them by ID (plan-mandated order)."""
        await self.ensure_collection()
        from qdrant_client.http import models as qdrant

        query_filter = qdrant.Filter(
            must=[
                qdrant.FieldCondition(
                    key="corpus_document_id",
                    match=qdrant.MatchValue(value=corpus_document_id),
                )
            ]
        )
        ids: list[str] = []
        offset: Any = None
        while True:
            points, offset = await self._client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=256,
                offset=offset,
                with_payload=False,
            )
            ids.extend(str(p.id) for p in points)
            if offset is None:
                break

        if not ids:
            return 0
        await self._client.delete(
            collection_name=self.collection_name,
            points_selector=qdrant.PointIdsList(points=ids),
            wait=True,
        )
        return len(ids)

    async def collection_info(self) -> dict[str, Any]:
        await self.ensure_collection()
        count_result = await self._client.count(
            collection_name=self.collection_name, exact=True
        )
        try:
            info = await self._client.get_collection(self.collection_name)
            dimension = int(info.config.params.vectors.size)
        except Exception:
            dimension = self.dimension
        return {
            "total_points": int(count_result.count),
            "dimension": dimension,
            "collection": self.collection_name,
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_filter(filters: dict[str, Any] | None):
        """Convert a plain dict of field→value into a Qdrant Filter."""
        from qdrant_client.http import models as qdrant

        if not filters:
            return None
        must = [
            qdrant.FieldCondition(
                key=str(key), match=qdrant.MatchValue(value=value)
            )
            for key, value in filters.items()
        ]
        return qdrant.Filter(must=must)


def get_vector_store() -> VectorStore:
    """Return the configured VectorStore based on ``vector_store_provider``.

    Only ``"qdrant"`` is supported in v1; the switch is in place for
    pgvector / ChromaDB later.
    """
    provider = settings.vector_store_provider
    if provider == "qdrant":
        return QdrantVectorStore()
    raise ValueError(f"Unsupported vector store provider: {provider}")
