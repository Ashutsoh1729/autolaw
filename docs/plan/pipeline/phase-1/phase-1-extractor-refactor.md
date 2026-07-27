# Phase 1 — Extractor Refactor: Pydantic AI + OpenRouter

**Status:** Done
**Depends on:** Nothing (self-contained backend refactor)

---

## Why

The current `app/services/extractor.py` has four problems:

| Problem | Consequence |
|---|---|
| **Vendor lock-in** — separate code paths for OpenAI SDK and Anthropic SDK | Duplicate logic, need to add a new SDK for every provider; switching vendors means code changes |
| **Fragile JSON parsing** — `_parse_json_response()` uses regex, bracket-matching, and NDJSON heuristics | Silent data loss when LLM wraps output in unexpected formatting; no validation that fields match the expected schema |
| **No structured output typing** — raw `dict`s flow through the pipeline | Callers have to trust the dict shape; no IDE autocompletion; runtime errors when a field is missing |
| **Config sprawl** — separate `openai_api_key`, `openai_model`, `anthropic_api_key`, `anthropic_model` in settings | Adding a new provider (OpenRouter, Groq, Gemini) requires 2+ new config fields every time |

---

## What

Replace the direct SDK calls in `extractor.py` with:

1. **Pydantic AI** (`pydantic-ai`) — abstraction layer that handles provider negotiation, retries, structured output via Pydantic models, and result validation. It already supports OpenAI, Anthropic, Gemini, Groq, and OpenRouter through a unified interface.

2. **OpenRouter** as the primary provider endpoint — a single API key gives access to 200+ models. Vendor flexibility comes for free: change the model name string, not the code.

3. **A Pydantic model** (`EventExtractionResult`) that replaces the raw `list[dict]` return type. Pydantic AI uses this model to validate the LLM's output before it enters our pipeline, eliminating the fragile JSON parsing code.

---

## Files to Modify

| File | Change |
|---|---|
| `backend/app/services/extractor.py` | Replace entire file. Remove OpenAI/Anthropic SDK calls. Use `pydantic-ai` Agent + RunResult. Keep the prompt template and pattern-based fallback. |
| `backend/app/config.py` | Replace `openai_api_key`, `openai_model`, `anthropic_api_key`, `anthropic_model` with `openrouter_api_key`, `llm_model` (string, default `"openai/gpt-4o-mini"`), `llm_provider_base_url`. |
| `backend/pyproject.toml` | Add `pydantic-ai>=0.0.18`. Remove `openai` and `anthropic` SDKs (if they weren't already added — currently they're lazy-imported, so no hard dep to remove). |
| `backend/app/services/dedup.py` | Possibly update type hints if the return type of `extract_events_from_chunk()` changes (see below). |
| `backend/app/routers/documents.py` | Possibly update import — but only the function signature changes; the call site stays the same. |

---

## Not Changing

- **Pipeline flow** — `documents.py:process_document_endpoint()` still calls `extract_events_from_chunk()` in a loop. The orchestration logic stays identical.
- **Prompts** — the `EXTRACTION_PROMPT` template stays as-is. Pydantic AI passes it to the model unchanged.
- **Database model** — `Event` table schema does not change. The new Pydantic model will map to the same fields.
- **Routes** — no HTTP endpoint changes.
- **Frontend** — no changes.
- **Fallback extraction** — the pattern-based regex fallback (for when no API key is set) stays in place.

---

## How — Implementation Steps

### Step 1: Define the Pydantic output model

Create a new `EventExtractionResult` model in a new file `backend/app/services/extraction_models.py` (or inline in `extractor.py`):

```python
from pydantic import BaseModel, Field


class ExtractedEvent(BaseModel):
    date: str = Field(description="ISO 8601 date or partial date as written")
    date_precision: str = Field(default="exact", pattern="^(exact|month|year|range)$")
    date_end: str | None = Field(default=None, description="End date for date ranges")
    title: str = Field(description="Short event title (max 100 chars)")
    description: str | None = Field(default=None)
    people: list[str] = Field(default_factory=list)
    doc_reference: str | None = Field(default=None)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EventExtractionResult(BaseModel):
    events: list[ExtractedEvent]
```

This replaces the current bare `list[dict]` return type. Pydantic AI will use this model as the `result_type` for its agent, so the LLM output is validated and coerced before it reaches our code.

### Step 2: Update `config.py`

Replace the four LLM config fields:

```python
# Before:
openai_api_key: str = ""
openai_model: str = "gpt-4o-mini"
anthropic_api_key: str = ""
anthropic_model: str = "claude-3-5-haiku-latest"

# After:
openrouter_api_key: str = ""
llm_model: str = "openai/gpt-4o-mini"       # OpenRouter model slug
llm_base_url: str = "https://openrouter.ai/api/v1"
```

Environment variable prefix `AUTOLAW_` remains. Users set `AUTOLAW_OPENROUTER_API_KEY` and `AUTOLAW_LLM_MODEL`.

### Step 3: Rewrite `extractor.py`

- Remove `_extract_with_openai()` and `_extract_with_anthropic()`
- Remove `_parse_json_response()` entirely (Pydantic AI handles this)
- Keep `EXTRACTION_PROMPT` and `_extract_pattern_based()` (fallback)
- Rewrite `extract_events_from_chunk()` to:

```python
from pydantic_ai import Agent

# One-time agent setup (module level)
agent = Agent(
    "openai",  # model name; OpenRouter is an OpenAI-compatible endpoint
    system_prompt="You are a legal document analyst...",
    result_type=EventExtractionResult,
)

async def extract_events_from_chunk(text: str, chunk_index: int = 0) -> list[dict]:
    if not settings.openrouter_api_key:
        return _extract_pattern_based(text, chunk_index)

    agent.model = OpenAIModel(
        settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.openrouter_api_key,
    )

    result = await agent.run(EXTRACTION_PROMPT.format(text=text[:8000]))
    validated: EventExtractionResult = result.data
    return [e.model_dump() for e in validated.events]
```

The return type stays `list[dict]` so no downstream caller needs to change. The validated `EventExtractionResult` is converted to dicts at the boundary.

### Step 4: Update `pyproject.toml`

```toml
dependencies = [
    ...
    "pydantic-ai>=0.0.18",
    # "openai" and "anthropic" can be removed if they were ever added directly
]
```

Run `uv sync` to lock the new dependency.

### Step 5: Clean up type hints (if needed)

Check whether any calls to `_extract_with_openai()` / `_extract_with_anthropic()` references exist in `dedup.py` or `documents.py` that import or depend on the old function signatures. If the return type of `extract_events_from_chunk()` stays `list[dict]`, no changes are needed. If the return type changes to `EventExtractionResult`, update:

- `backend/app/services/dedup.py` — `process_events()` accepts `list[dict]`, so keep the `.model_dump()` conversion at the boundary
- `backend/app/routers/documents.py` — no changes needed (it already calls `extract_events_from_chunk()` and passes the result to `process_events()`)

### Step 6: Test

1. `uv run python -m pytest tests/ -v` — all 16 existing tests should pass unchanged (they don't exercise LLM paths)
2. Manual smoke test with a real OpenRouter key: upload a .txt file, process it, verify events appear in the timeline
3. Verify pattern-based fallback still works with no API key set

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `pydantic-ai` API has breaking changes in early versions | Medium | Pin to a known-good version; check docs before upgrading |
| OpenRouter rate limits / downtime | Low | Fallback to pattern-based extraction (already exists); consider adding a secondary provider URL |
| Agent model negotiation picks wrong provider | Low | Test with OpenRouter's full model slug (e.g., `"openai/gpt-4o-mini"`); Pydantic AI parses the provider from the model string |
| `pydantic-ai` adds latency vs direct SDK call | Low | Negligible — it's a thin wrapper around the same HTTP calls |

---

## Files Summary

| Action | File |
|---|---|
| **Create** | `backend/app/services/extraction_models.py` — Pydantic models for structured output |
| **Rewrite** | `backend/app/services/extractor.py` — Use Pydantic AI Agent + OpenRouter |
| **Modify** | `backend/app/config.py` — Replace 4 LLM fields with 3 simpler ones |
| **Modify** | `backend/pyproject.toml` — Add `pydantic-ai` |
| **Possibly modify** | `backend/app/services/dedup.py` — type hints only |
| **Possibly modify** | `backend/app/routers/documents.py` — imports only |
