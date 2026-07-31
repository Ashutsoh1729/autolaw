"""Query formulation service — converts matter context into legal search queries.

Step 2 of the Phase 2 research pipeline. The default implementation is
template-based (no LLM): it extracts parties, legal causes of action, and the
matter jurisdiction from the matter description + timeline events and builds
1-3 legal search queries. An LLM-based formulation path is available when
``AUTOLAW_OPENROUTER_API_KEY`` is configured (a future enhancement).
"""

import logging
import re
from typing import Any

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# Whether pydantic-ai is available for LLM-based formulation.
_HAS_PYDANTIC_AI = False
try:
    from pydantic_ai import Agent, ModelSettings
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    _HAS_PYDANTIC_AI = True
except ImportError:  # pragma: no cover - exercised when pydantic-ai is absent
    logger.warning("pydantic-ai not installed; LLM query formulation unavailable.")

# Common legal causes of action / concepts used for term extraction.
LEGAL_TERMS: list[str] = [
    "negligence",
    "breach of contract",
    "breach of fiduciary duty",
    "breach of warranty",
    "breach of lease",
    "negligent misrepresentation",
    "intentional infliction of emotional distress",
    "wrongful termination",
    "wrongful death",
    "strict liability",
    "product liability",
    "premises liability",
    "medical malpractice",
    "professional malpractice",
    "legal malpractice",
    "defamation",
    "fraud",
    "securities fraud",
    "unjust enrichment",
    "conversion",
    "trespass",
    "nuisance",
    "assault",
    "battery",
    "false imprisonment",
    "invasion of privacy",
    "trade secret misappropriation",
    "copyright infringement",
    "trademark infringement",
    "unfair competition",
    "antitrust",
    "discrimination",
    "harassment",
    "retaliation",
    "whistleblower",
    "embezzlement",
    "bribery",
    "conspiracy",
    "perjury",
    "personal injury",
    "workers compensation",
    "duty of care",
    "causation",
    "liability",
    "statute of limitations",
    "summary judgment",
    "motion to dismiss",
]

# Words that add no search value when building a general query.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "with", "from", "into",
    "upon", "was", "were", "been", "being", "that", "this", "these",
    "those", "his", "her", "its", "their", "they", "them", "who", "whom",
    "which", "what", "when", "where", "how", "not", "but", "are", "had",
    "has", "have", "will", "would", "shall", "should", "may", "might",
    "must", "can", "could", "did", "does", "do", "client", "plaintiff",
    "defendant", "party", "parties", "case", "matter",
}

_PARTY_V_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9&.'-]{1,60})\s+v\.?\s+([A-Z][A-Za-z0-9&.'-]{1,60})\b"
)


class QueryListOutput(BaseModel):
    """Structured output model for LLM query formulation."""

    queries: list[str]


class QueryFormulator:
    """Generate legal search queries from matter context and timeline events."""

    def __init__(self, use_llm: bool | None = None) -> None:
        # ``use_llm`` defaults to "enabled when an API key is configured".
        self._use_llm = use_llm

    @property
    def use_llm(self) -> bool:
        if self._use_llm is not None:
            return self._use_llm
        return bool(settings.openrouter_api_key) and _HAS_PYDANTIC_AI

    async def formulate(
        self, matter_context: dict[str, Any], timeline_events: list[dict[str, Any]]
    ) -> list[str]:
        """Generate 1-3 legal search queries from matter facts and events."""
        if self.use_llm:
            try:
                return await self._formulate_with_llm(matter_context, timeline_events)
            except Exception as e:  # pragma: no cover - LLM failure fallback
                logger.error("LLM query formulation failed: %s. Using template mode.", e)

        return self._formulate_template(matter_context, timeline_events)

    async def extract_key_issues(self, matter_context: dict[str, Any]) -> list[str]:
        """Identify key legal issues from the matter description + events."""
        text = self._combined_text(matter_context, [])
        terms = self._extract_search_terms(text)
        if terms:
            return [f"{term} claim" for term in terms[:5]]
        return ["general liability"]

    # ------------------------------------------------------------------
    # Template-based formulation
    # ------------------------------------------------------------------

    def _formulate_template(
        self, matter_context: dict[str, Any], timeline_events: list[dict[str, Any]]
    ) -> list[str]:
        text = self._combined_text(matter_context, timeline_events)
        terms = self._extract_search_terms(text)
        parties = self._extract_parties(text, timeline_events)
        jurisdiction = (matter_context.get("jurisdiction") or "").strip()

        queries: list[str] = []

        # Primary query: "{party} {issue} liability {jurisdiction}"
        if terms or parties:
            party = parties[0] if parties else None
            issue = terms[0] if terms else None
            primary = self._join(party, issue, "liability", jurisdiction)
            if primary:
                queries.append(primary)

            # Secondary query from a distinct issue (if any).
            if len(terms) > 1:
                secondary = self._join(terms[1], "liability", jurisdiction)
                if secondary and secondary not in queries:
                    queries.append(secondary)

        # General query derived from the matter description/title keywords.
        general = self._general_query(matter_context)
        if general and general not in queries:
            queries.append(general)

        # Guarantee at least one query even with an empty context.
        if not queries:
            queries.append(self._join("liability", jurisdiction) or "liability")

        return queries[:3]

    def _extract_search_terms(self, text: str) -> list[str]:
        """Extract legal causes of action / concepts mentioned in the text."""
        lowered = text.lower()
        found: list[str] = []
        for term in LEGAL_TERMS:
            if term in lowered and term not in found:
                found.append(term)
        return found

    def _extract_parties(
        self, text: str, timeline_events: list[dict[str, Any]]
    ) -> list[str]:
        """Extract party names from people lists and 'X v. Y' patterns."""
        parties: list[str] = []

        # People involved in timeline events.
        for event in timeline_events:
            for person in event.get("people") or []:
                name = str(person).strip()
                if name and name not in parties:
                    parties.append(name)

        # "Smith v. Jones" style patterns in description/title.
        for match in _PARTY_V_PATTERN.finditer(text):
            for name in (match.group(1), match.group(2)):
                if name not in parties:
                    parties.append(name)

        return parties

    def _general_query(self, matter_context: dict[str, Any]) -> str:
        description = (matter_context.get("description") or "").strip()
        title = (matter_context.get("title") or "").strip()
        jurisdiction = (matter_context.get("jurisdiction") or "").strip()

        keywords = self._keywords(description) or self._keywords(title)
        if not keywords:
            return ""
        return self._join(" ".join(keywords[:5]), jurisdiction)

    def _keywords(self, text: str) -> list[str]:
        """Extract meaningful lowercase keywords from free text."""
        tokens = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)
        seen: list[str] = []
        for token in tokens:
            lowered = token.lower()
            if lowered not in _STOPWORDS and lowered not in seen:
                seen.append(lowered)
        return seen

    @staticmethod
    def _join(*parts: str | None) -> str:
        """Join non-empty query parts with a single space."""
        return " ".join(p.strip() for p in parts if p and p.strip())

    def _combined_text(
        self, matter_context: dict[str, Any], timeline_events: list[dict[str, Any]]
    ) -> str:
        chunks = [
            matter_context.get("title") or "",
            matter_context.get("description") or "",
            matter_context.get("case_number") or "",
        ]
        for event in timeline_events:
            chunks.append(event.get("title") or "")
            chunks.append(event.get("description") or "")
        return " ".join(chunks)

    # ------------------------------------------------------------------
    # LLM-based formulation (optional, future enhancement)
    # ------------------------------------------------------------------

    async def _formulate_with_llm(
        self, matter_context: dict[str, Any], timeline_events: list[dict[str, Any]]
    ) -> list[str]:
        """Generate queries via an LLM (OpenRouter) with structured output."""
        context_text = self._combined_text(matter_context, timeline_events)
        events_text = "\n".join(
            f"- {e.get('date', '')}: {e.get('title', '')}"
            f"{( ' — ' + e.get('description', '')) if e.get('description') else ''}"
            for e in timeline_events[:20]
        )

        prompt = (
            "Based on the following legal matter context, produce 1-3 concise "
            "legal research queries (max 15 words each) that would find relevant "
            "precedents and statutes. Output JSON with a single key \"queries\" "
            "containing an array of strings.\n\n"
            f"Matter context:\n{context_text}\n"
        )
        if events_text:
            prompt += f"\nTimeline events:\n{events_text}\n"

        provider = OpenAIProvider(
            base_url=settings.llm_base_url,
            api_key=settings.openrouter_api_key,
        )
        model_name = settings.llm_model.split("/", 1)[1] if "/" in settings.llm_model else settings.llm_model
        model = OpenAIChatModel(
            model_name,
            provider=provider,
            settings=ModelSettings(temperature=0.2),
        )
        agent = Agent(
            model,
            system_prompt=(
                "You are a legal research assistant. Return queries as JSON: "
                '{"queries": ["...", "..."]}.'
            ),
            output_type=QueryListOutput,
        )
        result = await agent.run(prompt)
        queries = [q.strip() for q in (result.output.queries if result.output else []) if q.strip()]
        return (queries or self._formulate_template(matter_context, timeline_events))[:3]
