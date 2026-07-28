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
- Generate vector embeddings for each chunk (OpenAI embeddings API or sentence-transformers).
- Set up a vector database (Qdrant via docker-compose) and store chunks with embeddings.
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

### Step 2: Add vector DB dependency

- [ ] Uncomment and configure the Qdrant service in `docker-compose.yml`:
  - Set `image: qdrant/qdrant:latest`
  - Map port `6333:6333` (gRPC) and `6334:6334` (HTTP)
  - Mount volume `qdrant_data:/qdrant/storage`
  - Add `qdrant_data` to the `volumes:` section
- [ ] Add Qdrant Python client to `backend/pyproject.toml`: `qdrant-client>=1.13.0`
- [ ] Add embedding dependency: `sentence-transformers>=3.4.0` (or keep optional — runtime configurable)
- [ ] Add config fields to `backend/app/config.py`:
  - `vector_store_provider: str = "qdrant"` — for future swap to pgvector/ChromaDB
  - `qdrant_url: str = "http://localhost:6333"` — Qdrant gRPC endpoint
  - `embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"` — local embedding model
  - `embedding_dimension: int = 384` — dimension for the chosen model
  - `openai_embedding_model: str = "text-embedding-3-small"` — alternative cloud embedding
- [ ] Run `uv sync` to lock new dependencies.

### Step 3: Implement Corpus Service

- [ ] Create `backend/app/services/corpus.py` with:
  - `CorpusService` class with methods:
    - `ingest_directory(path: str) -> IngestionReport` — walks directory, parses files, chunks, embeds, stores
    - `ingest_file(filepath: str) -> CorpusDocumentResponse` — parse a single file
    - `list_documents() -> list[CorpusDocumentResponse]` — list ingested docs
    - `delete_document(corpus_document_id: str) -> bool` — remove and clean up chunks
- [ ] Implement a parser for a specific corpus format (e.g., JSON lines with fields: case_name, citation, court, year, text). Support `.jsonl` and `.json` formats initially.
- [ ] Implement `_parse_document()` that extracts: case metadata + full text.
- [ ] Implement `_chunk_text(text: str, max_chunk_size: int = 512, overlap: int = 64) -> list[str]` — simple paragraph/sentence chunking with token-count awareness.
- [ ] Wire chunks through `EmbeddingService.embed()` then `VectorStore.store_chunks()`.
- [ ] Write unit tests for:
  - `_chunk_text` with known input/output
  - `ingest_file` with a fixture `.jsonl` file
  - Token-count estimation logic

### Step 4: Implement Embedding Service

- [ ] Create `backend/app/services/embedding.py` with:
  - `EmbeddingService` class with methods:
    - `embed(text: str) -> list[float]` — single string embedding
    - `embed_batch(texts: list[str]) -> list[list[float]]` — batched embedding
    - `embed_dimension() -> int` — return configured dimension
- [ ] Implement two backends (configurable via `embedding_model` config):
  - **Local**: sentence-transformers model loaded on first use (lazy init, cached singleton)
  - **API**: OpenAI embeddings API via `openai` client (if `openrouter_api_key` set, use that endpoint)
- [ ] Add caching: cache frequent embeddings in an in-memory LRU dict (key = text hash, value = vector).
- [ ] Handle rate limits: add exponential backoff for API-based embedding.
- [ ] Write unit tests:
  - Test `embed()` returns vector of correct dimension
  - Test `embed_batch()` returns correct count
  - Test caching returns same vector for same input
  - Mock API responses for API backend tests

### Step 5: Implement Vector Store (Qdrant client)

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

### Step 6: Create corpus seed data and ingestion CLI

- [ ] Create `backend/app/services/corpus_data/` directory (or similar) for seed corpus files.
- [ ] Add a small seed corpus (10–20 Supreme Court case summaries in `.jsonl` format) for dev/testing.
- [ ] Create a CLI entry point or script: `python -m app.services.corpus ingest --dir corpus_data/` for manual ingestion.
- [ ] Write a test that ingests the seed corpus and verifies all documents are stored and searchable.

### Step 7: Integration test

- [ ] Write `backend/tests/test_corpus_pipeline.py`:
  - End-to-end: parse → chunk → embed → store → search
  - Use a temporary Qdrant collection (or mock) so tests are hermetic
  - Verify search returns expected results for a known query
  - Verify filters narrow results correctly
  - Verify `delete_document` removes chunks from vector store

---

## Files to Modify

| Action | File | Notes |
|--------|------|-------|
| **Create** | `backend/app/schemas/corpus.py` | Pydantic models for corpus documents, chunks, ingestion report |
| **Create** | `backend/app/services/corpus.py` | Corpus ingestion service (parse, chunk, orchestrate) |
| **Create** | `backend/app/services/embedding.py` | Embedding service (local & API backends) |
| **Create** | `backend/app/services/vector_store.py` | Abstract VectorStore interface + Qdrant implementation |
| **Create** | `backend/app/services/corpus_data/seed.jsonl` | Small seed corpus for dev/testing |
| **Create** | `backend/tests/test_corpus_pipeline.py` | End-to-end ingestion + search tests |
| **Modify** | `docker-compose.yml` | Uncomment Qdrant service, add qdrant_data volume |
| **Modify** | `backend/pyproject.toml` | Add `qdrant-client`, `sentence-transformers` (or optional) |
| **Modify** | `backend/app/config.py` | Add vector store & embedding config fields |

## Functional Components

| Function / Component | File | Role |
|----------------------|------|------|
| `CorpusService` | `backend/app/services/corpus.py` | Orchestrates parse → chunk → embed → store pipeline |
| `EmbeddingService` | `backend/app/services/embedding.py` | Generates vector embeddings (local or API) |
| `VectorStore` (interface) | `backend/app/services/vector_store.py` | Abstract contract for vector DB operations |
| `QdrantVectorStore` | `backend/app/services/vector_store.py` | Qdrant-specific implementation of VectorStore |
| `get_vector_store()` | `backend/app/services/vector_store.py` | Factory function returning configured VectorStore |

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
| **Embedding API** | `text: str` | `list[float]` (384-dim for all-MiniLM-L6-v2) |
| **VectorStore.store_chunks** | `list[CorpusChunkSchema]` | `list[str]` (assigned chunk IDs) |
| **VectorStore.search** (contract for Group B) | `embedding: list[float]`, `top_k: int`, `filters: dict` | `list[SearchResult]` |
| **CorpusService.ingest_file** | File path to `.jsonl`/`.json` | `CorpusDocumentResponse` |
| **Corpus digest format** | `{case_name, citation, court, jurisdiction, year, text}` in JSONL | Structured chunks in vector store |

## Considerations

- **Corpus size**: Start small (10–20 docs). The chunker and embedding pipeline must handle batches of 100+ chunks without OOM. Test with 1000+ chunks to verify batch embedding works.
- **Embedding dimension**: Must match between embedding model and Qdrant collection config. Store the dimension in config and validate at startup.
- **Qdrant in tests**: Use `qdrant-client`'s `QdrantClient(memory=True)` for hermetic tests that don't require a running Docker container.
- **Token budgets**: For text longer than the embedding model's max tokens (512 for all-MiniLM-L6-v2), truncate with a warning rather than failing silently.
- **Sentence-transformers memory**: The local model loads into RAM (~500MB for all-MiniLM-L6-v2). Consider lazy-loading on first `embed()` call, not at import time.
- **No file conflicts**: All files created or modified by Group A are exclusive. The `VectorStore` interface is the only shared boundary — Group B imports the class but does not modify the file.
- **After merge**: Groups B, C, D depend on the `VectorStore` interface signature being stable. Any signature changes after Group A merges require updating Group B's imports.
