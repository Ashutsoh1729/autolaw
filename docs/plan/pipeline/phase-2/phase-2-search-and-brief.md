# Phase 2 — Group B: Search & Brief Generation

**Status:** Planned
**Depends on:** Group A's `VectorStore` interface (imports `SearchResult`, `get_vector_store()` from `backend/app/services/vector_store.py`; does NOT modify that file)
**Parallel groups:** No file conflicts with Groups A, C, or D. Defines API contract consumed by Group C.
**Parallelization contract:** Group B imports `VectorStore` and `SearchResult` from `backend/app/services/vector_store.py` (created by Group A). Both groups can work simultaneously because Group B only reads the interface signature, which is stable. If Group A changes the interface, Group B must update its calls after merge.

---

## Description

Build the query pipeline: convert matter context into structured legal queries, perform vector search via the VectorStore, rerank results, and synthesize a structured research brief using an LLM. Expose REST endpoints for search and brief generation that the frontend (Group C) consumes.

## Goals

- Convert matter facts/timeline events into structured legal search queries.
- Perform semantic vector search with metadata filtering (court, jurisdiction, year range).
- Rerank top-k results using a cross-encoder or LLM-based judge for improved precision.
- Generate structured research briefs with LLM synthesis, inline citations, and source tracking.
- Expose research API endpoints: search, brief status, brief generation, brief regeneration.
- Handle graceful degradation when no relevant results are found.
- Write unit and integration tests for search relevance and brief generation.

## Workflow

```
Matter context (facts + timeline events)
  → [Query Formulator] → structured legal query string(s)
  → [EmbeddingService.embed(query)] → query vector (from Group A)
  → [VectorStore.search(query_vector, filters, top_k=20)] → 20 raw results
  → [Reranker.rerank(query, raw_results)] → top 5 reranked results
  → [BriefGenerator.synthesize(query, passages, matter_context)] → ResearchBrief
  → [Brief API] → JSON response to frontend
```

## Implementation Steps

### Step 1: Research schemas

- [ ] Create `backend/app/schemas/research.py` with all request/response Pydantic models:
  - `ResearchSearchRequest`:
    - `query: str` — search query text
    - `query_type: str = "auto"` — "auto", "keyword", or "semantic"
    - `filters: dict | None = None` — `{court, jurisdiction, year_from, year_to}`
    - `top_k: int = 10`
  - `ResearchSearchResponse`:
    - `results: list[SearchResultItem]`
    - `total_results: int`
    - `query_used: str`
  - `SearchResultItem(BaseModel)`:
    - `chunk_id`, `corpus_document_id`, `text`, `case_name`, `citation`, `court`, `year`, `relevance_score`
  - `ResearchBriefRequest`:
    - `query: str`
    - `regenerate: bool = False`
    - `sections: list[str] | None = None` — optional list of sections to include (e.g., `["summary", "precedents", "statutes"]`)
  - `ResearchBriefResponse`:
    - `id: str`, `matter_id: str`, `query: str`, `created_at: datetime`
    - `summary: str`
    - `sections: list[BriefSection]`
    - `status: str` — `"complete"`, `"partial"`, `"no_results"`, `"generating"`
  - `BriefSection(BaseModel)`:
    - `title: str`
    - `content: str`
    - `citations: list[BriefCitation]`
  - `BriefCitation(BaseModel)`:
    - `citation: str`, `passage: str`, `relevance_score: float`, `corpus_document_id: str`
  - `ResearchStatusResponse`:
    - `brief_id: str | None`, `status: str`, `brief: ResearchBriefResponse | None`
- [ ] Write unit tests for schema validation.

### Step 2: Query formulation service

- [ ] Create `backend/app/services/query_formulator.py` with:
  - `QueryFormulator` class:
    - `async def formulate(matter_context: dict, timeline_events: list[dict]) -> list[str]` — generates 1–3 legal search queries from matter facts
    - `async def extract_key_issues(matter_context: dict) -> list[str]` — identifies key legal issues from matter description + events
  - For `formulate()`: Use a simple template-based approach first (no LLM), extracting key nouns, dates, parties from matter context and constructing query strings like `"{party} {issue} liability {jurisdiction}"`. LLM-based formulation is a future enhancement.
  - Implement `_extract_search_terms()`: parse timeline event titles and descriptions for key legal terms (party names, legal causes of action like "negligence", "breach of contract").
- [ ] Write unit tests:
  - Test with known matter context → expected query strings
  - Test with empty timeline returns a single general query
  - Test LLM formulation mode when `openrouter_api_key` is set (mock LLM response)

### Step 3: Reranker service

- [ ] Create `backend/app/services/reranker.py` with:
  - `Reranker` class:
    - `async def rerank(query: str, results: list[SearchResult], top_k: int = 5) -> list[SearchResult]` — re-scores and re-orders results
  - Implement two modes (configurable via `reranker_mode: str = "cross-encoder"` config):
    - **Cross-encoder**: Use `cross-encoder/ms-marco-MiniLM-L-6-v2` from sentence-transformers to compute relevance scores for each (query, passage) pair.
    - **LLM-based** (fallback/alternative): Use OpenRouter LLM to rate each passage's relevance on a 1–5 scale.
  - Implement `_rerank_cross_encoder()` — lazy-load model on first call, batch score pairs
  - Implement `_rerank_llm()` — construct a scoring prompt, call LLM via pydantic-ai
  - Normalize scores to 0–1 range
- [ ] Write unit tests:
  - Test with mock SearchResult list → verify output is re-ordered by score descending
  - Test `top_k` truncation
  - Test empty input returns empty list
  - Mock cross-encoder/LLM for deterministic test results

### Step 4: Brief generator service

- [ ] Create `backend/app/services/brief_generator.py` with:
  - `BriefGenerator` class:
    - `async def generate(query: str, passages: list[SearchResult], matter_context: dict) -> ResearchBriefResponse` — main synthesis method
    - `async def regenerate(brief_id: str, query: str, passages: list[SearchResult]) -> ResearchBriefResponse` — re-runs with same/different passages
  - Design the LLM prompt (in `BRIEF_SYNTHESIS_PROMPT` constant) that:
    - Takes the query, top passages (text + citation), and matter context
    - Instructs the LLM to produce structured JSON matching `ResearchBriefResponse` schema
    - Requires every factual claim to reference a specific passage citation
    - Includes a "no relevant results" output when passages are not relevant
  - Use `pydantic-ai` Agent with `result_type=ResearchBriefResponse` for structured output (same pattern as `extractor.py` in Phase 1)
  - Implement citation verification post-step: check that each citation in the brief matches at least one passage's citation string. Remove or flag unverifiable citations.
  - Handle token budgets: truncate passages to fit context window (reserve 4000 tokens for prompt, split remaining among passages).
  - Implement `_generate_summary(passages) -> str` — brief extractive summary as fallback when LLM is unavailable.
  - Set up brief caching: store generated briefs per matter in a dict (in-memory with TTL, or by matter_id key). Return cached brief if query matches and `regenerate=False`.
- [ ] Write unit tests:
  - Test with known passages + mock LLM → valid `ResearchBriefResponse`
  - Test citation verification: valid citations pass, hallucinated citations flagged
  - Test LLM-unavailable fallback returns graceful `status: "no_results"` with explanatory summary
  - Test caching: second call with same query returns cached brief (no LLM call)
  - Test truncation: many long passages → fits within token budget

### Step 5: Research API router

- [ ] Create `backend/app/routers/research.py` with endpoints:
  - `POST /api/matters/{matter_id}/research/search` — accepts `ResearchSearchRequest`, returns `ResearchSearchResponse`
    1. Get matter context (description, case_number, jurisdiction from DB)
    2. Embed the query via `EmbeddingService.embed()`
    3. Call `VectorStore.search()` with embedding + filters
    4. Call `Reranker.rerank()` on results
    5. Return top-k with relevance scores
  - `GET /api/matters/{matter_id}/research/brief` — returns the current brief for the matter (or `status: "not_generated"`)
    1. Check cache for existing brief
    2. If not cached, return `status: "not_generated"` with no brief
  - `POST /api/matters/{matter_id}/research/brief` — generates a new brief
    1. Get matter context from DB
    2. Call `QueryFormulator.formulate()` to get query strings
    3. For each query, run search + rerank
    4. Merge passages from all queries
    5. Call `BriefGenerator.generate()` with merged passages
    6. Cache the brief keyed by matter_id
    7. Return `ResearchBriefResponse`
  - `POST /api/matters/{matter_id}/research/brief/regenerate` — accepts optional new query, re-runs generation
    1. Similar to POST above but forces re-generation even if cached
    2. If `query` provided, use it directly instead of formulating
    3. Update the cached brief
  - `GET /api/matters/{matter_id}/research/status` — lightweight endpoint returning `ResearchStatusResponse`
- [ ] Handle errors gracefully:
  - Corpus not ingested → 200 with `status: "no_results"` + message
  - Embedding service unavailable → 503
  - LLM unavailable → 200 with partial/extractive summary (degraded mode)
  - Matter not found → 404
- [ ] Register the router in `backend/app/main.py` (add `research` to the imports and `app.include_router(research.router)`).
- [ ] Wire `EmbeddingService` and `get_vector_store()` via dependency injection or direct import.

### Step 6: Wire EmbeddingService into search

- [ ] In the search endpoint, import `EmbeddingService` from Group A and create a shared instance (module-level singleton or FastAPI dependency).
- [ ] In the search endpoint, import `get_vector_store()` from Group A and create a shared instance.
- [ ] Ensure error handling: if vector DB is unreachable, return degraded response with `status: "no_results"`.
- [ ] Add logging throughout the pipeline (query text, result count, latency per step).

### Step 7: Integration tests for the search + brief pipeline

- [ ] Write `backend/tests/test_research_pipeline.py`:
  - Seed a test Qdrant collection with known embeddings (or use `QdrantClient(memory=True)`)
  - Test search endpoint with a known query → expected result IDs returned
  - Test search with filters (court, year range) → results narrowed correctly
  - Test brief generation with mock LLM → valid `ResearchBriefResponse` returned
  - Test brief caching: second call returns same brief
  - Test regenerate endpoint returns different brief
  - Test `status` endpoint returns correct states
  - Test graceful degradation: stop Qdrant → endpoint returns `status: "no_results"` with message
  - Test empty corpus returns `"no_results"` status

---

## Files to Modify

| Action | File | Notes |
|--------|------|-------|
| **Create** | `backend/app/schemas/research.py` | All request/response Pydantic models |
| **Create** | `backend/app/services/query_formulator.py` | Matter-context-to-query conversion |
| **Create** | `backend/app/services/reranker.py` | Cross-encoder / LLM reranking |
| **Create** | `backend/app/services/brief_generator.py` | LLM brief synthesis with citations |
| **Create** | `backend/app/routers/research.py` | Research API endpoints |
| **Create** | `backend/tests/test_research_pipeline.py` | Integration tests for pipeline |
| **Modify** | `backend/app/main.py` | Register research router (adds one line) |

**Consumed from Group A (read-only):**
| Import | Source File | What's Used |
|--------|-------------|-------------|
| `SearchResult` | `backend/app/services/vector_store.py` | Dataclass for search results |
| `get_vector_store()` | `backend/app/services/vector_store.py` | Factory: returns `VectorStore` instance |
| `EmbeddingService` | `backend/app/services/embedding.py` | To embed query strings |

## Functional Components

| Function / Component | File | Role |
|----------------------|------|------|
| `QueryFormulator.formulate()` | `backend/app/services/query_formulator.py` | Convert matter context to search queries |
| `Reranker.rerank()` | `backend/app/services/reranker.py` | Re-score and re-order search results |
| `BriefGenerator.generate()` | `backend/app/services/brief_generator.py` | LLM synthesis of structured brief |
| `BriefGenerator.regenerate()` | `backend/app/services/brief_generator.py` | Re-run brief generation |
| `search_endpoint` | `backend/app/routers/research.py` | `POST /research/search` |
| `brief_get_endpoint` | `backend/app/routers/research.py` | `GET /research/brief` |
| `brief_create_endpoint` | `backend/app/routers/research.py` | `POST /research/brief` |
| `brief_regenerate_endpoint` | `backend/app/routers/research.py` | `POST /research/brief/regenerate` |
| `status_endpoint` | `backend/app/routers/research.py` | `GET /research/status` |

## Data Model

### Key Types (defined in `schemas/research.py`)

```python
class ResearchSearchRequest(BaseModel):
    query: str
    filters: dict | None = None       # {court, jurisdiction, year_from, year_to}
    top_k: int = 10

class SearchResultItem(BaseModel):
    chunk_id: str
    corpus_document_id: str
    text: str
    case_name: str
    citation: str
    court: str
    year: int
    relevance_score: float

class ResearchBriefResponse(BaseModel):
    id: str
    matter_id: str
    query: str
    created_at: datetime
    summary: str
    sections: list[BriefSection]
    status: str                       # "complete" | "partial" | "no_results" | "generating"

class BriefSection(BaseModel):
    title: str
    content: str
    citations: list[BriefCitation]

class BriefCitation(BaseModel):
    citation: str
    passage: str
    relevance_score: float
    corpus_document_id: str
```

### Brief Cache (in-memory)
```python
# keyed by matter_id, value = (query_hash, ResearchBriefResponse, created_at)
brief_cache: dict[str, tuple[str, ResearchBriefResponse, datetime]]
```

## Boundaries

| Boundary | Input | Output |
|----------|-------|--------|
| **Search API** (→ Group C) | `POST /api/matters/{id}/research/search` with `ResearchSearchRequest` | `ResearchSearchResponse` with results + scores |
| **Brief API** (→ Group C) | `POST /api/matters/{id}/research/brief` (no body, uses matter context) | `ResearchBriefResponse` |
| **Brief Regenerate API** (→ Group C) | `POST /api/matters/{id}/research/brief/regenerate` with optional `{query}` | `ResearchBriefResponse` |
| **Status API** (→ Group C) | `GET /api/matters/{id}/research/status` | `ResearchStatusResponse` {brief_id, status, brief?} |
| **VectorStore** (← Group A) | `vector_store.search(embedding, top_k, filters)` | `list[SearchResult]` |
| **EmbeddingService** (← Group A) | `embedding_service.embed(text)` | `list[float]` |

## Considerations

- **LLM cost**: Brief generation is the most expensive operation. Cache aggressively. Consider showing the search results directly (without LLM synthesis) for quick lookups.
- **Citation accuracy**: The LLM may hallucinate citations. The citation verification step in `BriefGenerator` is critical. Consider logging hallucination rate during testing.
- **Multiple queries per matter**: A matter may involve multiple legal issues. The query formulator should generate 1–3 queries and merge results.
- **Token budget**: The LLM context window must fit prompt + passages + instructions. For a 128k model, reserve 30k for the prompt + instructions, remaining ~98k for passages. Implement truncation that favors higher-scored passages.
- **Degraded modes**: The system should work (in a limited way) without LLM (extractive summary only) and without vector DB (return error with helpful message).
- **No file conflicts**: Group B creates only new files except one line added to `main.py`. The three files imported from Group A (`vector_store.py`, `embedding.py`) are read-only imports — Group B never modifies them.
- **After merge**: Group C's API calls must match the exact endpoint paths and request/response shapes defined here.
