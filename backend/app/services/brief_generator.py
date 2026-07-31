"""Brief generator service — LLM synthesis of structured research briefs.

Step 4 of the Phase 2 research pipeline.

Takes a query, the top reranked passages, and the matter context, and produces a
structured :class:`ResearchBriefResponse` via an LLM (pydantic-ai + OpenRouter)
with:

- a synthesis prompt that requires every claim to cite a retrieved passage,
- a post-generation citation verification step (hallucinated citations removed),
- token-budget truncation of passages (reserve tokens for the prompt),
- graceful degradation: extractive "partial" briefs or "no_results" when the
  LLM is unavailable,
- an in-memory brief cache keyed by matter id (with TTL).

``SearchResult`` is imported from Group A's ``app/services/vector_store.py``
(read-only), with a structurally identical fallback for parallel development.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.schemas.research import BriefCitation, BriefSection, ResearchBriefResponse

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

# LLM backend (optional).
_HAS_PYDANTIC_AI = False
try:
    from pydantic_ai import Agent, ModelSettings
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    _HAS_PYDANTIC_AI = True
except ImportError:  # pragma: no cover - pydantic-ai is optional
    logger.debug("pydantic-ai not installed; LLM brief synthesis unavailable.")

# ---------------------------------------------------------------------------
# Prompt + token budget constants
# ---------------------------------------------------------------------------

BRIEF_SYNTHESIS_PROMPT = """You are a legal research analyst. Given a legal research query, the matter context, and retrieved passages from a case law corpus, synthesize a structured research brief.

Instructions:
1. Produce JSON matching the ResearchBriefResponse schema exactly:
   {
     "id": "<uuid string>",
     "matter_id": "<matter id from context>",
     "query": "<the query>",
     "created_at": "<ISO 8601 UTC timestamp>",
     "summary": "<2-4 sentence overview>",
     "sections": [
       {
         "title": "<section title>",
         "content": "<detailed analysis, 2-5 paragraphs>",
         "citations": [
           {"citation": "<exact citation string from a passage>", "passage": "<short supporting quote>", "relevance_score": <0-1>, "corpus_document_id": "<id from the passage>"}
         ]
       }
     ],
     "status": "complete"
   }
2. status must be one of: "complete" (every section fully supported), "partial" (some sections could not be completed), or "no_results" (the retrieved passages are not relevant to the query).
3. Every factual claim in every section must be supported by at least one retrieved passage. Cite sources using the EXACT citation string from the passage metadata. Do not paraphrase citations.
4. Only cite passages that actually appear in the retrieved passages. Never invent or hallucinate case names, citations, holdings, or corpus_document_id values.
5. Choose section titles appropriate to the query, e.g. "Summary of Relevant Law", "Key Precedents", "Statutes", "Analysis".
6. Set relevance_score (0-1) for each citation to reflect how relevant that passage is to the claim it supports.
7. If no retrieved passage is relevant to the query, set status to "no_results", leave sections empty, and explain why in the summary.
8. created_at must be the current UTC time in ISO 8601 format; id must be a fresh UUID string."""

# Token budget: reserve this many tokens for the prompt + instructions, split
# the remaining context window among passages (rough chars-per-token = 4).
PROMPT_RESERVED_TOKENS = 4000
CONTEXT_WINDOW_TOKENS = 128_000
CHARS_PER_TOKEN = 4
MAX_PASSAGE_CHARS = 8_000

# Cache TTL for generated briefs (24h).
BRIEF_TTL_SECONDS = 24 * 60 * 60


def _hash_query(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


class BriefGenerator:
    """Synthesize structured research briefs from query + passages."""

    def __init__(self) -> None:
        # keyed by matter_id: (query_hash, ResearchBriefResponse, created_at)
        self._cache: dict[str, tuple[str, ResearchBriefResponse, datetime]] = {}

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def get_cached(self, matter_id: str, query: str) -> ResearchBriefResponse | None:
        """Return the cached brief for a matter+query match (respects TTL)."""
        entry = self._cache.get(matter_id)
        if not entry:
            return None
        query_hash, brief, created_at = entry
        if datetime.now(timezone.utc) - created_at > timedelta(seconds=BRIEF_TTL_SECONDS):
            self._cache.pop(matter_id, None)
            return None
        if query_hash != _hash_query(query):
            return None
        return brief

    def get_brief(self, matter_id: str) -> ResearchBriefResponse | None:
        """Return the latest cached brief for a matter (regardless of query)."""
        entry = self._cache.get(matter_id)
        if not entry:
            return None
        _, brief, created_at = entry
        if datetime.now(timezone.utc) - created_at > timedelta(seconds=BRIEF_TTL_SECONDS):
            self._cache.pop(matter_id, None)
            return None
        return brief

    def clear_cache(self) -> None:
        self._cache.clear()

    def _cache_brief(self, matter_id: str, query: str, brief: ResearchBriefResponse) -> None:
        self._cache[matter_id] = (_hash_query(query), brief, datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        query: str,
        passages: list[SearchResult],
        matter_context: dict[str, Any],
        force: bool = False,
    ) -> ResearchBriefResponse:
        """Synthesize a brief, honoring the cache unless ``force`` is set."""
        matter_id = matter_context.get("matter_id") or "unknown"
        if not force:
            cached = self.get_cached(matter_id, query)
            if cached is not None:
                return cached
        brief = await self._synthesize(query, passages, matter_context)
        self._cache_brief(matter_id, query, brief)
        return brief

    async def regenerate(
        self,
        brief_id: str,
        query: str,
        passages: list[SearchResult],
        matter_context: dict[str, Any] | None = None,
    ) -> ResearchBriefResponse:
        """Re-run generation, bypassing the cache and updating it.

        ``matter_context`` is optional: when omitted, the matter id is looked up
        from the cache by ``brief_id``.
        """
        matter_id = (
            matter_context.get("matter_id")
            if matter_context and matter_context.get("matter_id")
            else self._matter_id_for_brief(brief_id)
        ) or "unknown"
        ctx = dict(matter_context or {})
        ctx.setdefault("matter_id", matter_id)
        brief = await self._synthesize(query, passages, ctx)
        self._cache_brief(matter_id, query, brief)
        return brief

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def _synthesize(
        self, query: str, passages: list[SearchResult], matter_context: dict[str, Any]
    ) -> ResearchBriefResponse:
        matter_id = matter_context.get("matter_id") or "unknown"

        if not passages:
            return self._no_results_brief(matter_id, query)

        if self._llm_available():
            try:
                brief = await self._synthesize_with_llm(query, passages, matter_context)
            except Exception as e:
                logger.error("LLM brief generation failed: %s. Using extractive fallback.", e)
                brief = self._extractive_brief(matter_id, query, passages)
        else:
            brief = self._extractive_brief(matter_id, query, passages)

        return self._verify_citations(brief, passages)

    async def _synthesize_with_llm(
        self, query: str, passages: list[SearchResult], matter_context: dict[str, Any]
    ) -> ResearchBriefResponse:
        """Run the LLM agent with structured output matching the brief schema."""
        truncated = self._truncate_passages(passages)
        prompt = self._build_prompt(query, truncated, matter_context)

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
            settings=ModelSettings(temperature=0.1),
        )
        agent = Agent(
            model,
            system_prompt=BRIEF_SYNTHESIS_PROMPT,
            output_type=ResearchBriefResponse,
        )
        result = await agent.run(prompt)
        brief = result.output
        if brief is None:  # pragma: no cover - defensive
            raise ValueError("LLM returned no brief output")
        return brief

    # ------------------------------------------------------------------
    # Citation verification
    # ------------------------------------------------------------------

    def _verify_citations(
        self, brief: ResearchBriefResponse, passages: list[SearchResult]
    ) -> ResearchBriefResponse:
        """Drop citations that don't match a retrieved passage; fill missing ids.

        A citation is kept when its ``citation`` string matches a passage's
        metadata citation. If the LLM left ``corpus_document_id`` empty, it is
        filled from the matching passage; a non-empty id must match the passage.
        """
        passage_by_citation: dict[str, SearchResult] = {}
        for passage in passages:
            citation = (passage.metadata or {}).get("citation") or ""
            if citation:
                passage_by_citation.setdefault(citation, passage)

        removed = 0
        for section in brief.sections:
            kept: list[BriefCitation] = []
            for citation in section.citations:
                passage = passage_by_citation.get(citation.citation)
                if passage is None:
                    removed += 1
                    continue
                if citation.corpus_document_id and citation.corpus_document_id != passage.corpus_document_id:
                    removed += 1
                    continue
                kept.append(
                    BriefCitation(
                        citation=citation.citation,
                        passage=citation.passage or passage.text[:500],
                        relevance_score=citation.relevance_score,
                        corpus_document_id=passage.corpus_document_id,
                    )
                )
            section.citations = kept
        if removed:
            logger.warning("Removed %d unverifiable citation(s) from brief %s", removed, brief.id)
        return brief

    # ------------------------------------------------------------------
    # Fallbacks (no LLM)
    # ------------------------------------------------------------------

    def _no_results_brief(self, matter_id: str, query: str) -> ResearchBriefResponse:
        return ResearchBriefResponse(
            id=str(uuid.uuid4()),
            matter_id=matter_id,
            query=query,
            created_at=datetime.now(timezone.utc),
            summary=(
                "No relevant precedents or statutes were found for this query. "
                "Try broadening the search terms, adjusting filters, or expanding "
                "the case law corpus."
            ),
            sections=[],
            status="no_results",
        )

    def _extractive_brief(
        self, matter_id: str, query: str, passages: list[SearchResult]
    ) -> ResearchBriefResponse:
        """Degraded-mode brief: extractive summary + top passages, no LLM."""
        ordered = sorted(passages, key=lambda p: p.score, reverse=True)[:5]
        citations = [
            BriefCitation(
                citation=(p.metadata or {}).get("citation") or p.corpus_document_id,
                passage=p.text[:500],
                relevance_score=p.score,
                corpus_document_id=p.corpus_document_id,
            )
            for p in ordered
        ]
        section = BriefSection(
            title="Relevant Passages",
            content="\n\n".join(f"{i + 1}. {p.text[:500]}" for i, p in enumerate(ordered)),
            citations=citations,
        )
        return ResearchBriefResponse(
            id=str(uuid.uuid4()),
            matter_id=matter_id,
            query=query,
            created_at=datetime.now(timezone.utc),
            summary=self._generate_summary(ordered),
            sections=[section],
            status="partial",
        )

    def _generate_summary(self, passages: list[SearchResult]) -> str:
        """Brief extractive summary from the highest-scored passage."""
        if not passages:
            return ""
        top = sorted(passages, key=lambda p: p.score, reverse=True)[0]
        return top.text[:500]

    # ------------------------------------------------------------------
    # Token budget / prompt helpers
    # ------------------------------------------------------------------

    def _truncate_passages(
        self,
        passages: list[SearchResult],
        reserved_tokens: int = PROMPT_RESERVED_TOKENS,
        max_tokens: int = CONTEXT_WINDOW_TOKENS,
    ) -> list[SearchResult]:
        """Keep the highest-scored passages that fit the context window."""
        budget_chars = max(1, (max_tokens - reserved_tokens)) * CHARS_PER_TOKEN
        ordered = sorted(passages, key=lambda p: p.score, reverse=True)
        kept: list[SearchResult] = []
        used_chars = 0
        for passage in ordered:
            text = passage.text[:MAX_PASSAGE_CHARS]
            estimated = len(text) + 200  # overhead for citation/metadata wrapping
            if kept and used_chars + estimated > budget_chars:
                break
            kept.append(
                SearchResult(
                    chunk_id=passage.chunk_id,
                    corpus_document_id=passage.corpus_document_id,
                    text=text,
                    metadata=passage.metadata,
                    score=passage.score,
                )
            )
            used_chars += estimated
        return kept

    def _build_prompt(
        self,
        query: str,
        passages: list[SearchResult],
        matter_context: dict[str, Any],
    ) -> str:
        matter_text = self._matter_context_text(matter_context)
        passage_lines = "\n\n".join(
            f"--- Passage {i + 1} (citation: {(p.metadata or {}).get('citation', 'N/A')}, "
            f"corpus_document_id: {p.corpus_document_id}) ---\n{p.text}"
            for i, p in enumerate(passages)
        )
        return (
            f"QUERY: {query}\n\n"
            f"MATTER CONTEXT:\n{matter_text}\n\n"
            f"RETRIEVED PASSAGES:\n{passage_lines}"
        )

    @staticmethod
    def _matter_context_text(matter_context: dict[str, Any]) -> str:
        lines = []
        for key in ("title", "case_number", "case_type", "jurisdiction", "description"):
            value = matter_context.get(key)
            if value:
                lines.append(f"{key}: {value}")
        return "\n".join(lines) or "(no additional matter context provided)"

    def _llm_available(self) -> bool:
        return bool(settings.openrouter_api_key) and _HAS_PYDANTIC_AI

    def _matter_id_for_brief(self, brief_id: str) -> str | None:
        for matter_id, (_, brief, _) in self._cache.items():
            if brief.id == brief_id:
                return matter_id
        return None
