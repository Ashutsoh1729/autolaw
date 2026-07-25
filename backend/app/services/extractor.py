"""LLM event extraction service — extracts structured events from document chunks."""

import json
import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Extraction prompt template
EXTRACTION_PROMPT = """You are a legal document analyst. Extract all chronological events from the following document text.

For each event, output a JSON object with these fields:
- "date": The date of the event (ISO 8601 format if possible, otherwise as written)
- "date_precision": "exact" if a full date is given, "month" if only month/year, "year" if only year, "range" if it's a date range
- "date_end": If the event spans a date range, the end date (ISO 8601). Otherwise null.
- "title": A short title for the event (max 100 chars)
- "description": A detailed description of what happened (2-3 sentences)
- "people": Array of full names of people involved (as strings)
- "doc_reference": Any page, paragraph, or section reference from the document
- "confidence": A number between 0.0 and 1.0 indicating how confident you are that this event occurred as described

IMPORTANT: 
- Return ONLY a JSON array of event objects. No other text.
- If no events are found, return an empty array [].
- Handle partial dates, relative dates ("on or about March 2024"), and date ranges.
- Extract ALL events mentioned, even minor ones.

Document text:
---
{text}
---
"""


def _parse_json_response(response_text: str) -> list[dict[str, Any]]:
    """Parse JSON from an LLM response, handling common formatting issues."""
    # Try direct parse first
    text = response_text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        pass

    # Try to extract JSON array from code fences
    json_match = re.search(r"```(?:json)?\s*\n?(\[[\s\S]*?\])\n?\s*```", text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find array starting/ending brackets
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    # Try line-by-line JSON parsing (for NDJSON-like output)
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    return events


async def extract_events_from_chunk(
    text: str,
    chunk_index: int = 0,
) -> list[dict[str, Any]]:
    """Extract events from a single text chunk using LLM.

    Falls back to a simple pattern-based extraction if no LLM is configured.
    """
    if settings.openai_api_key:
        return await _extract_with_openai(text)
    elif settings.anthropic_api_key:
        return await _extract_with_anthropic(text)
    else:
        return _extract_pattern_based(text, chunk_index)


async def _extract_with_openai(text: str) -> list[dict[str, Any]]:
    """Extract events using OpenAI."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You are a legal document analyst. Extract events as JSON."},
                {"role": "user", "content": EXTRACTION_PROMPT.format(text=text[:8000])},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "[]"
        return _parse_json_response(content)
    except Exception as e:
        logger.error("OpenAI extraction failed: %s. Falling back to pattern-based.", e)
        return _extract_pattern_based(text, 0)


async def _extract_with_anthropic(text: str) -> list[dict[str, Any]]:
    """Extract events using Anthropic Claude."""
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4000,
            system="You are a legal document analyst. Extract events as JSON arrays.",
            messages=[
                {"role": "user", "content": EXTRACTION_PROMPT.format(text=text[:8000])},
            ],
        )
        content = response.content[0].text if response.content else "[]"
        return _parse_json_response(content)
    except Exception as e:
        logger.error("Anthropic extraction failed: %s. Falling back to pattern-based.", e)
        return _extract_pattern_based(text, 0)


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
