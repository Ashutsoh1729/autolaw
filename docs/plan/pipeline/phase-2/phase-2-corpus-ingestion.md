# Phase 2 — Group A: Corpus Ingestion

**Status:** Planned
**Depends on:** Nothing (standalone backend module)
**Parallel groups:** Defines `VectorStore` interface contract consumed by Group B; no file conflicts with Groups B, C, or D.

---

## Description

Build the pipeline that ingests a curated case law corpus, parses legal documents into text chunks with citation metadata, generates vector embeddings, and stores everything in a vector database. This is the foundation for the RAG search pipeline.

## Goals

- Acquire or create a small curated case law corpus (Supreme Court / selected jurisdiction).
- Parse legal documents into structured chunks with citation metadata.
- Generate vector embeddings for each chunk via OpenRouter (default: `nvidia/nemotron-3-embed-1b:free`, fallback: `qwen/qwen3-embedding-8b`).
- Set up a vector database (Qdrant via docker-compose) and store chunks with embeddings.
- Store original uploaded files in R2 blob storage with `storage_path` reference in the database.
- Implement the `VectorStore` interface that Group B will import for search.
- Write ingestion tests verifying chunking, embedding dimensions, and round-trip storage.

## Workflow

```
Raw corpus (JSON/bulk files)
  → [Corpus parser] → structured CorpusDocument records
  → [Chunker] → text chunks with metadata
  → [EmbeddingService] → float[] vectors
  → [VectorStore.store_chunks] → persisted in Qdrant collection
  → Ingestion report (docs ingested, chunks created, vector count)
```

## Implementation Steps

### Step 1: Define Pydantic models for corpus documents and chunks

- [ ] Create `backend/app/schemas/corpus.py` with:
  - `CorpusDocumentCreate(BaseModel)` — fields: case_name, citation, court, jurisdiction, year, url (optional), summary (optional)
  - `CorpusDocumentResponse(BaseModel)` — same fields + id
  - `CorpusChunkSchema(BaseModel)` — fields: id, corpus_document_id, chunk_index, text, metadata (dict), embedding (list[float] | None)
  - `IngestionReport(BaseModel)` — fields: documents_ingested, chunks_created, elapsed_seconds
- [ ] Write unit tests for schema validation (wrong types, missing required fields).

### Step 2: Create SQLAlchemy model for CorpusDocument

- [ ] Create `backend/app/models/corpus_document.py` with SQLAlchemy model:
  - `id: UUID` — primary key
  - `case_name: str` — full case name (e.g., "Marbury v. Madison")
  - `citation: str` — legal citation (e.g., "5 U.S. 137")
  - `court: str` — court name (e.g., "Supreme Court of the United States")
  - `jurisdiction: str` — jurisdiction (e.g., "federal", "California")
  - `year: int` — year of decision
  - `storage_path: str | None` — R2 object key for the original uploaded file
  - `embedding_model: str` — model used to generate embeddings for this document's chunks
  - `embedding_dimension: int` — dimension of the embeddings stored for this document
  - `status: str` — one of `pending`, `ingesting`, `ready`, `failed`
  - `created_at: datetime` — auto-set on creation
  - `updated_at: datetime` — auto-updated on modification
- [ ] Add the model to `backend/app/models/__init__.py` so Alembic can discover it.
- [ ] Create and run a migration: `alembic revision --autogenerate -m "add corpus_document"` then `alembic upgrade head`.
- [ ] Update the existing Pydantic schema (`backend/app/schemas/corpus.py`) to align with the new DB model, adding `storage_path`, `embedding_model`, `embedding_dimension`, `status`, `created_at`, `updated_at` fields.
- [ ] Write unit tests for the model (fixture with known values, verify CRUD via repository layer).

### Step 3: Add vector DB dependency

- [ ] Uncomment and configure the Qdrant service in `docker-compose.yml`:
  - Set `image: qdrant/qdrant:latest`
  - Map port `6333:6333` (gRPC) and `6334:6334` (HTTP)
  - Mount volume `qdrant_data:/qdrant/storage`
  - Add `qdrant_data` to the `volumes:` section
- [ ] Add Qdrant Python client to `backend/pyproject.toml`: `qdrant-client>=1.13.0`
- [ ] Add embedding dependency: `openai>=1.55.0` (OpenAI Python client, used for OpenRouter API calls)
- [ ] Add config fields to `backend/app/config.py`:
  - `vector_store_provider: str = "qdrant"` — for future swap to pgvector/ChromaDB
  - `qdrant_url: str = "http://localhost:6333"` — Qdrant gRPC endpoint
  - `embedding_model: str = "nvidia/nemotron-3-embed-1b:free"` — default embedding model via OpenRouter
  - `embedding_fallback_model: str = "qwen/qwen3-embedding-8b"` — fallback model if primary is unavailable
  - `embedding_dimension: int = 1024` — dimension for the Nemotron-3-Embed-1B model
  - `openrouter_api_key: str` — loaded from env, required for embedding API calls
- [ ] Run `uv sync` to lock new dependencies.

### Step 4: Implement Corpus Service

- [ ] Create `backend/app/services/corpus.py` with:
  - `CorpusService` class with methods:
    - `ingest_file(filepath: str, storage_path: str | None = None) -> CorpusDocumentResponse` — parse a single file; if `storage_path` is provided, save it to the CorpusDocument record
    - `ingest_directory(path: str) -> IngestionReport` — walks directory, parses files, chunks, embeds, stores
    - `list_documents() -> list[CorpusDocumentResponse]` — list ingested docs
    - `delete_document(corpus_document_id: str) -> bool` — remove and clean up chunks **and** delete the original file from R2
- [ ] Implement a parser for a specific corpus format (e.g., JSON lines with fields: case_name, citation, court, year, text). Support `.jsonl` and `.json` formats initially.
- [ ] Implement `_parse_document()` that extracts: case metadata + full text.
- [ ] Implement `_chunk_text(text: str, max_chunk_size: int = 512, overlap: int = 64) -> list[str]` — simple paragraph/sentence chunking with token-count awareness.
- [ ] **R2 storage**: When ingesting an uploaded file, save the original file to R2 blob storage (using the existing S3/R2 client from Phase 1). Store the resulting object key in `CorpusDocument.storage_path`.
- [ ] Wire chunks through `EmbeddingService.embed()` then `VectorStore.store_chunks()`.
- [ ] **Delete order**: `delete_document` must follow this order: (1) delete the original file from R2 via `storage_path`, (2) delete chunks from Qdrant via `VectorStore.delete_chunks()`, (3) delete the `CorpusDocument` record from the database. If any step fails, roll back the DB transaction and raise.
- [ ] Write unit tests for:
  - `_chunk_text` with known input/output
  - `ingest_file` with a fixture `.jsonl` file
  - Token-count estimation logic
  - `delete_document` with mock R2, VectorStore, and DB (verify order of operations)

### Step 5: Implement Embedding Service

- [ ] Create `backend/app/services/embedding.py` with:
  - `EmbeddingService` class with methods:
    - `embed(text: str) -> list[float]` — single string embedding via OpenRouter
    - `embed_batch(texts: list[str]) -> list[list[float]]` — batched embedding via OpenRouter
    - `embed_dimension() -> int` — return configured dimension from config
- [ ] Implement the embedding backend via OpenRouter's OpenAI-compatible API:
  - Configure the `openai` client with `base_url="https://openrouter.ai/api/v1"` and the user's API key from config
  - Try `embedding_model` first (default: `nvidia/nemotron-3-embed-1b:free`)
  - On failure (HTTP error, timeout, rate limit), fall back to `embedding_fallback_model` (`qwen/qwen3-embedding-8b`)
  - Log which model was used for observability
- [ ] Add caching: cache frequent embeddings in an in-memory LRU dict (key = text hash, value = vector).
- [ ] Handle rate limits: add exponential backoff for OpenRouter API calls.
- [ ] Store `embedding_model` and `embedding_dimension` per CorpusDocument record when ingesting, so each document tracks which model produced its embeddings.
- [ ] Write unit tests:
  - Test `embed()` returns vector of correct dimension (1024 for Nemotron)
  - Test `embed_batch()` returns correct count
  - Test caching returns same vector for same input
  - Mock OpenRouter API responses for test isolation
  - Test fallback logic: primary model fails → fallback model is called

### Step 6: Implement Vector Store (Qdrant client)

- [ ] Create `backend/app/services/vector_store.py` with the **`VectorStore` abstract interface** (this is the contract for Group B):
  - `VectorStore(ABC)`:
    - `async def store_chunks(self, chunks: list[CorpusChunkSchema]) -> list[str]` — returns chunk IDs
    - `async def search(self, embedding: list[float], top_k: int = 10, filters: dict | None = None) -> list[SearchResult]` — returns results with scores
    - `async def delete_chunks(self, corpus_document_id: str) -> int` — deletes all chunks for a document
    - `async def collection_info(self) -> dict` — stats (total points, dimension)
  - `SearchResult` dataclass:
    - `chunk_id: str`, `corpus_document_id: str`, `text: str`, `metadata: dict`, `score: float`
- [ ] Implement `QdrantVectorStore(VectorStore)`:
  - On init: connect to Qdrant, ensure collection exists with correct dimension and cosine distance metric
  - `store_chunks`: upsert points with payload (text, metadata, corpus_document_id)
  - `search`: convert filters to Qdrant filter conditions, perform search with `with_payload=True`, map results to `SearchResult`
  - `delete_chunks`: use `scroll` + `delete` by filter on `corpus_document_id`
- [ ] Add connection pooling / retry logic for Qdrant gRPC.
- [ ] Implement a factory function `get_vector_store() -> VectorStore` that reads `vector_store_provider` from settings and returns the appropriate implementation (only Qdrant in v1, extensible for pgvector/ChromaDB later).
- [ ] Write integration tests:
  - Start Qdrant in test container or mock the client
  - Test store → search round-trip with known embeddings
  - Test filtering by court, year, jurisdiction
  - Test empty collection returns empty results
  - Test `delete_chunks` removes points

### Step 7: Create corpus seed data and ingestion CLI

- [ ] Create `backend/app/services/corpus_data/` directory (or similar) for seed corpus files.
- [ ] Add a small seed corpus (10–20 Supreme Court case summaries in `.jsonl` format) for dev/testing.
- [ ] Create a CLI entry point or script: `python -m app.services.corpus ingest --dir corpus_data/` for manual ingestion.
- [ ] Write a test that ingests the seed corpus and verifies all documents are stored and searchable.

### Step 8: Integration test

- [ ] Write `backend/tests/test_corpus_pipeline.py`:
  - End-to-end: parse → chunk → embed → store → search
  - Use a temporary Qdrant collection (or mock) so tests are hermetic
  - Verify search returns expected results for a known query
  - Verify filters narrow results correctly
  - Verify `delete_document` removes chunks from vector store

### Step 9: Create corpus ingestion API endpoint

- [ ] Create `backend/app/routers/corpus.py` with:
  - `POST /api/corpus/ingest` endpoint:
    - Accepts `multipart/form-data` with:
      - `file: UploadFile` — the corpus document file (`.jsonl` or `.json`)
      - `case_name: str | None` — optional override for case name
      - `citation: str | None` — optional override for citation
      - `court: str | None` — optional override for court
      - `jurisdiction: str | None` — optional override for jurisdiction
      - `year: int | None` — optional override for year
    - Flow:
      1. Validate file format (must be `.jsonl` or `.json`). Return 400 for invalid format.
      2. Check for duplicate — if a document with the same `case_name` + `citation` already exists, return 409 Conflict.
      3. Save the uploaded file to R2 blob storage using the existing S3/R2 client from Phase 1, generating a unique object key (e.g., `corpus/{uuid}/{original_filename}`).
      4. Create a `CorpusDocument` record in the database with `status="pending"`, `storage_path` set to the R2 key, and `embedding_model` / `embedding_dimension` from current config.
      5. Call `CorpusService.ingest_file()` with the saved file path and `storage_path`.
      6. On success, update the `CorpusDocument` status to `"ready"` and return `IngestionReport` (201 Created).
      7. On failure, update status to `"failed"` and return 500 with error details.
    - Error handling:
      - 400: invalid file format (not `.jsonl`/`.json`), missing required fields
      - 409: duplicate document (same `case_name` + `citation` already exists)
      - 500: internal error during ingestion (R2 upload failure, embedding failure, Qdrant failure)
- [ ] Register the router in `backend/app/main.py`: `app.include_router(corpus_router, prefix="/api/corpus", tags=["corpus"])`.
- [ ] Write integration tests for the endpoint:
  - Upload valid `.jsonl` file → 201 + `IngestionReport`
  - Upload duplicate → 409
  - Upload invalid file type → 400
  - Upload with metadata overrides → verify overrides applied
  - Verify R2 object was created after successful ingest

---

## Files to Modify

| Action | File | Notes |
|--------|------|-------|
| **Create** | `backend/app/models/corpus_document.py` | SQLAlchemy model for CorpusDocument |
| **Create** | `backend/app/schemas/corpus.py` | Pydantic models for corpus documents, chunks, ingestion report |
| **Create** | `backend/app/routers/corpus.py` | POST /api/corpus/ingest endpoint |
| **Create** | `backend/app/services/corpus.py` | Corpus ingestion service (parse, chunk, orchestrate, R2 storage) |
| **Create** | `backend/app/services/embedding.py` | Embedding service (OpenRouter API via OpenAI client) |
| **Create** | `backend/app/services/vector_store.py` | Abstract VectorStore interface + Qdrant implementation |
| **Create** | `backend/app/services/corpus_data/seed.jsonl` | Small seed corpus for dev/testing |
| **Create** | `backend/tests/test_corpus_pipeline.py` | End-to-end ingestion + search tests |
| **Modify** | `backend/app/models/__init__.py` | Import `CorpusDocument` so Alembic discovers it |
| **Modify** | `backend/app/main.py` | Register `corpus_router` |
| **Modify** | `docker-compose.yml` | Uncomment Qdrant service, add qdrant_data volume |
| **Modify** | `backend/pyproject.toml` | Add `qdrant-client`, `openai` (OpenRouter) |
| **Modify** | `backend/app/config.py` | Add vector store & OpenRouter embedding config fields |

## Functional Components

| Function / Component | File | Role |
|----------------------|------|------|
| `CorpusDocument` (model) | `backend/app/models/corpus_document.py` | SQLAlchemy model for persisted corpus document records |
| `CorpusService` | `backend/app/services/corpus.py` | Orchestrates parse → chunk → embed → store pipeline (with R2 blob storage) |
| `EmbeddingService` | `backend/app/services/embedding.py` | Generates vector embeddings via OpenRouter API (primary + fallback model) |
| `VectorStore` (interface) | `backend/app/services/vector_store.py` | Abstract contract for vector DB operations |
| `QdrantVectorStore` | `backend/app/services/vector_store.py` | Qdrant-specific implementation of VectorStore |
| `get_vector_store()` | `backend/app/services/vector_store.py` | Factory function returning configured VectorStore |
| `CorpusIngestRouter` | `backend/app/routers/corpus.py` | POST /api/corpus/ingest — file upload, R2 save, ingestion orchestration |

## Data Model

### CorpusDocumentSchema
```python
class CorpusDocumentSchema(BaseModel):
    id: str
    case_name: str
    citation: str
    court: str
    jurisdiction: str
    year: int
    url: str | None = None
    summary: str | None = None
    storage_path: str | None = None       # R2 object key
    embedding_model: str | None = None    # model used for this document's embeddings
    embedding_dimension: int | None = None
    status: str                           # pending | ingesting | ready | failed
    created_at: datetime
    updated_at: datetime
```

### CorpusChunkSchema
```python
class CorpusChunkSchema(BaseModel):
    id: str | None = None        # assigned by VectorStore
    corpus_document_id: str
    chunk_index: int
    text: str
    metadata: dict                # {case_name, citation, court, year}
    embedding: list[float] | None = None
```

### SearchResult (dataclass in vector_store.py)
```python
@dataclass
class SearchResult:
    chunk_id: str
    corpus_document_id: str
    text: str
    metadata: dict                # {case_name, citation, court, year}
    score: float                  # cosine similarity
```

## Boundaries

| Boundary | Input | Output |
|----------|-------|--------|
| **Embedding API** | `text: str` | `list[float]` (1024-dim for Nemotron-3-Embed-1B via OpenRouter) |
| **VectorStore.store_chunks** | `list[CorpusChunkSchema]` | `list[str]` (assigned chunk IDs) |
| **VectorStore.search** (contract for Group B) | `embedding: list[float]`, `top_k: int`, `filters: dict` | `list[SearchResult]` |
| **CorpusService.ingest_file** | File path + optional `storage_path` | `CorpusDocumentResponse` |
| **POST /api/corpus/ingest** | `multipart/form-data` (file + optional metadata fields) | `IngestionReport` (201) or error (400/409/500) |
| **R2 storage** | Uploaded corpus file | Object stored at `corpus/{uuid}/{filename}`, `storage_path` saved to DB |
| **Corpus digest format** | `{case_name, citation, court, jurisdiction, year, text}` in JSONL | Structured chunks in vector store |

## Considerations

- **Corpus size**: Start small (10–20 docs). The chunker and embedding pipeline must handle batches of 100+ chunks without OOM. Test with 1000+ chunks to verify batch embedding works.
- **Embedding dimension**: Must match between embedding model and Qdrant collection config. Store the dimension in config and validate at startup.
- **Qdrant in tests**: Use `qdrant-client`'s `QdrantClient(memory=True)` for hermetic tests that don't require a running Docker container.
- **Token budgets**: For text longer than the embedding model's max tokens (512 for Nemotron-3-Embed-1B), truncate with a warning rather than failing silently.
- **OpenRouter rate limits**: Free-tier OpenRouter has rate limits. Implement exponential backoff with jitter. Consider queueing large batch operations.
- **No local model**: Embeddings are always produced via OpenRouter API. No sentence-transformers model is loaded locally, saving ~500MB RAM.
- **No file conflicts**: All files created or modified by Group A are exclusive. The `VectorStore` interface is the only shared boundary — Group B imports the class but does not modify the file.
- **After merge**: Groups B, C, D depend on the `VectorStore` interface signature being stable. Any signature changes after Group A merges require updating Group B's imports.

## Background Job Orchestration (Post-MVP)

Once the basic ingestion pipeline is working, consider wrapping it with **Inngest** for production reliability:

- **Why**: The `POST /api/corpus/ingest` endpoint currently blocks until ingestion completes. Large documents may take 30+ seconds (chunk → embed → store).
- **How**: Create an Inngest function that takes the R2 object key + metadata, runs the full `CorpusService.ingest_file()` pipeline, and updates the `CorpusDocument.status` as it progresses (`pending → ingesting → ready | failed`).
- **No service changes needed**: The existing `CorpusService`, `EmbeddingService`, and `VectorStore` are called directly — just wrapped in an async Inngest handler.
- **No timeout**: Inngest functions have no execution timeout, so even very large documents can be processed without HTTP timeouts.
- **Retries**: Inngest automatically retries on failure (configurable backoff).
- **Status polling**: The frontend polls `GET /api/corpus/documents/{id}` to show progress. The API returns the current `status` field.
- **Queue**: Inngest manages concurrency — optional max concurrency of 1 to avoid rate-limiting the embedding API.
- **Migration path**: Replace the inline `CorpusService.ingest_file()` call in the router with `inngest.send()`. The router returns 202 Accepted immediately, and the frontend polls for completion.
