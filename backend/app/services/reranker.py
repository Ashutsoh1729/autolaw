"""Reranker service — re-scores and re-orders vector search results.

Step 3 of the Phase 2 research pipeline.

Two scoring modes (configurable via ``AUTOLAW_RERANKER_MODE`` env var, default
``cross-encoder``):

- **cross-encoder**: ``cross-encoder/ms-marco-MiniLM-L-6-v2`` via
  sentence-transformers (lazy-loaded on first call). Requires the optional
  ``sentence-transformers`` package.
- **llm**: an OpenRouter LLM rates each passage's relevance on a 1-5 scale
  (requires ``AUTOLAW_OPENROUTER_API_KEY``).

When neither backend is available/configured, a deterministic lexical scorer
blends query/passage token overlap with the base vector score, so the pipeline
still functions (and tests stay hermetic).

``SearchResult`` is imported from Group A's ``app/services/vector_store.py``
(read-only). If Group A's module is not yet present (parallel development), a
structurally identical dataclass fallback is used.
"""

import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SearchResult — imported from Group A (read-only), with a local fallback.
# ---------------------------------------------------------------------------
_HAS_GROUP_A_VECTOR_STORE = False
try:
    from app.services.vector_store import SearchResult  # type: ignore

    _HAS_GROUP_A_VECTOR_STORE = True
except ImportError:  # pragma: no cover - exercised before Group A merges

    @dataclass
    class SearchResult:
        """Structurally identical to Group A's dataclass."""

        chunk_id: str
        corpus_document_id: str
        text: str
        metadata: dict = field(default_factory=dict)
        score: float = 0.0

# Optional scoring backends.
_HAS_SENTENCE_TRANSFORMERS = False
try:
    from sentence_transformers import CrossEncoder  # type: ignore

    _HAS_SENTENCE_TRANSFORMERS = True
except ImportError:  # pragma: no cover - sentence-transformers is optional
    logger.debug("sentence-transformers not installed; cross-encoder mode unavailable.")

_HAS_PYDANTIC_AI = False
try:
    from pydantic_ai import Agent, ModelSettings
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    _HAS_PYDANTIC_AI = True
except ImportError:  # pragma: no cover - pydantic-ai is optional
    logger.debug("pydantic-ai not installed; LLM reranking unavailable.")

DEFAULT_RERANKER_MODE = os.getenv("AUTOLAW_RERANKER_MODE", "cross-encoder")
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class _ScoreItem(BaseModel):
    index: int
    score: float  # 1-5 relevance


class _ScoreList(BaseModel):
    scores: list[_ScoreItem]


class Reranker:
    """Re-score and re-order a list of ``SearchResult`` objects."""

    def __init__(
        self,
        mode: str | None = None,
        scorer: Callable[[str, SearchResult], float] | None = None,
    ) -> None:
        self.mode = (mode or DEFAULT_RERANKER_MODE).lower()
        # Deterministic scorer override (used by tests to avoid real models).
        self._scorer = scorer
        self._cross_encoder: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rerank(
        self, query: str, results: list[SearchResult], top_k: int = 5
    ) -> list[SearchResult]:
        """Re-score results, order by descending score, return top-k."""
        if not results:
            return []

        if self._scorer is not None:
            scored = [self._scored_copy(r, self._scorer(query, r)) for r in results]
        elif self.mode == "llm" and self._llm_available():
            scored = await self._rerank_llm(query, results)
        elif self.mode == "cross-encoder" and _HAS_SENTENCE_TRANSFORMERS:
            scored = await self._rerank_cross_encoder(query, results)
        else:
            # Lexical fallback — deterministic, no external dependencies.
            scored = [self._scored_copy(r, self._score_pair(query, r.text)) for r in results]

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Scoring modes
    # ------------------------------------------------------------------

    async def _rerank_cross_encoder(
        self, query: str, results: list[SearchResult]
    ) -> list[SearchResult]:
        """Score (query, passage) pairs with a cross-encoder model."""
        try:
            model = self._get_cross_encoder()
            pairs = [(query, self._truncate(r.text)) for r in results]
            raw_scores = model.score(pairs)
            return [
                self._scored_copy(r, self._sigmoid(float(raw)))
                for r, raw in zip(results, raw_scores)
            ]
        except Exception as e:  # pragma: no cover - model/network failures
            logger.error("Cross-encoder reranking failed: %s. Using lexical fallback.", e)
            return [self._scored_copy(r, self._score_pair(query, r.text)) for r in results]

    async def _rerank_llm(
        self, query: str, results: list[SearchResult]
    ) -> list[SearchResult]:
        """Score each passage via an LLM judge (1-5 scale, normalized to 0-1)."""
        try:
            passage_lines = "\n".join(
                f"[{i}] {self._truncate(r.text)}"
                for i, r in enumerate(results)
            )
            prompt = (
                "You are a legal research relevance judge. Rate how relevant each "
                "passage is to the query on a scale of 1 (irrelevant) to 5 (highly "
                "relevant). Output JSON only:\n"
                '{"scores": [{"index": 0, "score": 4}, ...]}\n\n'
                f"QUERY: {query}\n\n"
                f"PASSAGES:\n{passage_lines}\n"
            )

            provider = OpenAIProvider(
                base_url=settings.llm_base_url,
                api_key=settings.openrouter_api_key,
            )
            model_name = (
                settings.llm_model.split("/", 1)[1]
                if "/" in settings.llm_model
                else settings.llm_model
            )
            model = OpenAIChatModel(
                model_name,
                provider=provider,
                settings=ModelSettings(temperature=0.0),
            )
            agent = Agent(
                model,
                system_prompt=(
                    "You are a strict legal relevance judge. Return only the JSON object."
                ),
                output_type=_ScoreList,
            )
            result = await agent.run(prompt)
            scores_by_index = {
                item.index: item.score for item in (result.output.scores if result.output else [])
            }
            scored = [
                self._scored_copy(r, scores_by_index.get(i, 1.0) / 5.0)
                for i, r in enumerate(results)
            ]
            return scored
        except Exception as e:  # pragma: no cover - LLM failures
            logger.error("LLM reranking failed: %s. Using lexical fallback.", e)
            return [self._scored_copy(r, self._score_pair(query, r.text)) for r in results]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _llm_available(self) -> bool:
        return bool(settings.openrouter_api_key) and _HAS_PYDANTIC_AI

    def _get_cross_encoder(self) -> Any:
        if self._cross_encoder is None:
            self._cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
        return self._cross_encoder

    def _scored_copy(self, result: SearchResult, score: float) -> SearchResult:
        """Return a copy of ``result`` with a clamped 0-1 score."""
        return SearchResult(
            chunk_id=result.chunk_id,
            corpus_document_id=result.corpus_document_id,
            text=result.text,
            metadata=result.metadata,
            score=max(0.0, min(1.0, float(score))),
        )

    def _score_pair(self, query: str, passage: str) -> float:
        """Deterministic lexical relevance: query/passage token overlap."""
        query_tokens = set(re.findall(r"[a-z0-9']+", query.lower()))
        passage_tokens = set(re.findall(r"[a-z0-9']+", passage.lower()))
        if not query_tokens:
            return 0.0
        return len(query_tokens & passage_tokens) / len(query_tokens)

    @staticmethod
    def _sigmoid(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-x))

    @staticmethod
    def _truncate(text: str, max_chars: int = 2000) -> str:
        return text if len(text) <= max_chars else text[:max_chars]
