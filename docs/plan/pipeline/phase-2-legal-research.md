# Phase 2: Legal Research (RAG Module)

## Description

Add a legal research module that uses Retrieval-Augmented Generation (RAG) over a curated case law corpus. Given a query or the context of a matter (the timeline and documents from Phase 1), the system retrieves relevant precedents, statutes, and case law, then generates a research brief for lawyer review.

## Goals

- Ingest a case law corpus (or connect to a public legal database API).
- Embed documents and store vectors for semantic search.
- Implement RAG query pipeline: embed query → vector search → LLM synthesis → structured brief.
- Surface results in the UI alongside the timeline.
- Respect token budgets and citation accuracy.

## Workflow

```
Phase-1 output (matter context + timeline events)
  → [Query formulation] — generate search queries from case facts
  → [Corpus ingestion] — case law documents → chunk → embed → vector store
  → [Vector search] — semantic similarity retrieval
  → [Reranking] — improve relevance of retrieved passages
  → [LLM synthesis] — generate research brief with citations
  → [Brief API] — serve structured brief to frontend
  → [Brief UI] — display with inline citations, source links
  → [Export] — include brief in the final Word/PDF export
```

## Implementation Steps

### Step 1: Corpus Ingestion Pipeline
- [ ] Identify and acquire case law corpus (e.g., CourtListener / Caselaw Access Project / custom dataset).
- [ ] Build ingestion script: parse legal documents into text chunks with citation metadata.
- [ ] Set up embedding service (OpenAI embeddings / sentence-transformers / local model).
- [ ] Set up vector database (ChromaDB / Qdrant / pgvector on PostgreSQL).
- [ ] Embed chunks and store with metadata (case name, court, year, citation).
- [ ] Write ingestion tests verifying correct chunking and embedding dimensions.

### Step 2: Query Pipeline
- [ ] Build query formulation service: convert matter facts/timeline events into structured legal queries.
- [ ] Implement vector search endpoint: `POST /api/matters/{id}/research/search?q=...`.
- [ ] Implement reranking step (cross-encoder or LLM-based) to improve top-k results.
- [ ] Add filtering by jurisdiction, court, date range, case type.
- [ ] Write tests for search relevance with known queries.

### Step 3: Research Brief Generation
- [ ] Design the research brief output schema (sections: summary, relevant precedents, statutes, analysis).
- [ ] Build LLM synthesis prompt that takes retrieved passages + matter context and generates a structured brief.
- [ ] Implement citation tracking: each claim in the brief must reference its source passage.
- [ ] Implement `GET /api/matters/{id}/research/brief` — cached or generated on demand.
- [ ] Handle the case where no relevant results are found (graceful degradation).

### Step 4: Research UI
- [ ] Add research tab/section to the matter detail page.
- [ ] Implement search input with autocomplete and filter controls.
- [ ] Display research brief with expandable citations and source links.
- [ ] Add "Regenerate" button to re-run query with new parameters.
- [ ] Show relevance scores and confidence indicators.
- [ ] Component tests for the research UI.

### Step 5: Integration with Phase 1
- [ ] Wire research brief into the export pipeline (include in Word/PDF export).
- [ ] Add research context to timeline events (link events to relevant precedents).
- [ ] End-to-end test: matter with documents → timeline → research query → export with brief.

---

## Files to Modify (anticipated)

- `backend/app/routers/research.py` — research API endpoints
- `backend/app/services/corpus.py` — corpus ingestion and management
- `backend/app/services/embedding.py` — text embedding service
- `backend/app/services/vector_store.py` — vector database client
- `backend/app/services/reranker.py` — search reranking logic
- `backend/app/services/brief_generator.py` — LLM research brief generation
- `frontend/src/pages/MatterDetail.tsx` — add research tab
- `frontend/src/components/ResearchBrief.tsx` — brief display component
- `frontend/src/components/ResearchSearch.tsx` — search input component
- `docker-compose.yml` — add vector DB service

## Functional Components

| Function / Component | Location (anticipated) | Role |
|----------------------|------------------------|------|
| `CorpusService` | `backend/app/services/corpus.py` | Ingest and manage case law documents |
| `EmbeddingService` | `backend/app/services/embedding.py` | Generate vector embeddings |
| `VectorStore` | `backend/app/services/vector_store.py` | Vector DB client for similarity search |
| `Reranker` | `backend/app/services/reranker.py` | Improve retrieval precision |
| `BriefGenerator` | `backend/app/services/brief_generator.py` | LLM synthesis of research brief |
| `ResearchSearch` | `frontend/src/components/ResearchSearch.tsx` | Search input with filters |
| `ResearchBrief` | `frontend/src/components/ResearchBrief.tsx` | Brief results display |

## Data Model

### CorpusDocument
```
{
  id: UUID,
  case_name: string,
  citation: string,
  court: string,
  jurisdiction: string,
  year: number,
  url?: string,
  summary?: string
}
```

### CorpusChunk
```
{
  id: UUID,
  corpus_document_id: UUID,
  chunk_index: number,
  text: string,
  embedding: float[],        // vector
  metadata: {
    case_name: string,
    citation: string,
    court: string,
    year: number
  }
}
```

### ResearchBrief
```
{
  id: UUID,
  matter_id: UUID,
  query: string,
  created_at: datetime,
  summary: string,
  sections: [
    {
      title: string,          // e.g., "Relevant Precedents", "Statutes", "Analysis"
      content: string,
      citations: [
        {
          citation: string,
          passage: string,
          relevance_score: number,
          corpus_document_id: UUID
        }
      ]
    }
  ],
  status: "complete" | "partial" | "no_results"
}
```

## Boundaries

| Boundary | Input | Output |
|----------|-------|--------|
| Corpus Ingestion | Raw legal text + metadata | Chunks with embeddings in vector DB |
| Search API | Query string + filters (court, year, etc.) | Ranked list of relevant passages + scores |
| Brief API | Matter ID (uses timeline + stored events for context) | Structured ResearchBrief JSON |
| Export Integration | Matter ID (adds brief to export payload) | Combined export with timeline + brief |

## Considerations

- **Corpus size**: A full case law corpus is massive. Start with a small curated subset (e.g., Supreme Court cases, a specific jurisdiction).
- **Citation accuracy**: The LLM may hallucinate citations. Implement strict prompt constraints and consider a verify step against known citations.
- **Query diversity**: A single matter may need multiple research queries (one per legal issue). Support multiple briefs per matter.
- **Update frequency**: Case law evolves. Design the corpus ingestion to support incremental updates.
- **Jurisdiction filtering**: Legal research is jurisdiction-specific. Ensure filters work correctly.
- **Cost**: Embedding and LLM calls for RAG can be significant. Cache briefs and reuse embeddings.
- **Phase 1 dependency**: Phase 2 depends on Phase 1 being at least partially complete (matter documents → timeline → query context).
