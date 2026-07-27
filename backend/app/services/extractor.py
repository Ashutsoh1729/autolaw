"""LLM event extraction service — extracts structured events from document chunks."""

import logging
import re
from typing import Any

from app.config import settings
from app.services.extraction_models import EventExtractionResult

logger = logging.getLogger(__name__)

# Extraction system prompt
EXTRACTION_SYSTEM_PROMPT = """You are a legal document analyst. Extract all chronological events from the following document text.

For each event, extract:
- date: The date of the event (ISO 8601 format if possible, otherwise as written)
- date_precision: "exact" if a full date is given, "month" if only month/year, "year" if only year, "range" if it's a date range
- date_end: If the event spans a date range, the end date (ISO 8601). Otherwise null.
- title: A short title for the event (max 100 chars)
- description: A detailed description of what happened (2-3 sentences)
- people: Array of full names of people involved
- doc_reference: Any page, paragraph, or section reference from the document
- confidence: A number between 0.0 and 1.0 indicating how confident you are that this event occurred as described

Handle partial dates, relative dates ("on or about March 2024"), and date ranges.
Extract ALL events mentioned, even minor ones. If no events are found, return an empty list."""


# Flag: whether pydantic-ai is available
_HAS_PYDANTIC_AI = False
try:
    from pydantic_ai import Agent, ModelSettings
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    _HAS_PYDANTIC_AI = True
except ImportError:
    logger.warning("pydantic-ai not installed; LLM extraction will fall back to pattern-based.")


async def extract_events_from_chunk(
    text: str,
    chunk_index: int = 0,
) -> list[dict[str, Any]]:
    """Extract events from a single text chunk using LLM.

    Uses pydantic-ai with an OpenAI-compatible provider (default: OpenRouter)
    for structured event extraction. Falls back to a simple pattern-based
    extraction if no LLM is configured or the call fails.
    """
    if not settings.openrouter_api_key or not _HAS_PYDANTIC_AI:
        return _extract_pattern_based(text, chunk_index)

    try:
        return await _extract_with_pydantic_ai(text)
    except Exception as e:
        logger.error("LLM extraction failed: %s. Falling back to pattern-based.", e)
        return _extract_pattern_based(text, chunk_index)


async def _extract_with_pydantic_ai(text: str) -> list[dict[str, Any]]:
    """Extract events using pydantic-ai with an OpenAI-compatible provider."""
    # Truncate to avoid exceeding token limits
    truncated_text = text[:8000]

    # Build the provider — defaults to OpenRouter but allows any
    # OpenAI-compatible API via AUTOLAW_LLM_BASE_URL.
    provider = OpenAIProvider(
        base_url=settings.llm_base_url,
        api_key=settings.openrouter_api_key,
    )

    # Strip any provider prefix from the model name — OpenRouter uses
    # "openai/gpt-4o-mini" but pydantic-ai expects just "gpt-4o-mini"
    # when using a custom OpenAI-compatible provider.
    model_name = settings.llm_model
    if "/" in model_name:
        model_name = model_name.split("/", 1)[1]

    model = OpenAIChatModel(
        model_name,
        provider=provider,
        settings=ModelSettings(temperature=0.1),
    )

    agent = Agent(
        model,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        output_type=EventExtractionResult,
    )

    result = await agent.run(truncated_text)
    events = result.output.events  # type: ignore[union-attr]

    # Convert back to list[dict] for downstream compatibility
    return [e.model_dump() for e in events]


def _extract_pattern_based(text: str, chunk_index: int) -> list[dict[str, Any]]:
    """Fallback pattern-based extraction for when no LLM is configured.

    Uses regex to find date-like patterns and extracts surrounding context.
    """
    events: list[dict[str, Any]] = []
    # Match dates like "January 1, 2024", "01/15/2024", "2024-03-15", etc.
    date_patterns = [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]

    for pattern in date_patterns:
        for match in re.finditer(pattern, text):
            # Get surrounding context (100 chars before and after)
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 200)
            context = text[start:end].strip()

            events.append({
                "date": match.group(),
                "date_precision": "exact",
                "date_end": None,
                "title": f"Event on {match.group()}",
                "description": context[:300],
                "people": [],
                "doc_reference": f"Chunk {chunk_index}",
                "confidence": 0.3,
            })

    return events
