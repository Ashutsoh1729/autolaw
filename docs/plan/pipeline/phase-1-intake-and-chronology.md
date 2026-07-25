# Phase 1: Intake + Chronology Builder

## Description

Build the core document ingestion pipeline and the chronology/timeline extraction engine. A lawyer uploads or emails case documents (PDF, TXT, email exports, scanned images) and the system:

1. Ingests and normalizes them (OCR for scans, text extraction for PDFs/emails).
2. Chunks and classifies each document by type (contract, email, police report, medical record, correspondence).
3. Extracts structured events (date, event description, people involved, source document reference).
4. Deduplicates overlapping entries and sorts chronologically.
5. Presents an interactive, filterable timeline.
6. Exports the timeline to Word/PDF for filing.

## Goals

- A working end-to-end pipeline from raw document upload to structured timeline export.
- All core Gen AI concepts demonstrated: OCR, prompt engineering, structured LLM output, entity resolution.
- Interactive timeline UI that a lawyer can filter, search, and export.
- Modulare architecture so the Legal Research module (Phase 2) can consume the same processed document store.

## Workflow

```
Raw docs (PDF, TXT, email, scan)
  → [Upload API / Email listener]
  → [OCR service] — Tesseract / GPT-4V for scanned images
  → [Text splitter & classifier] — chunk by doc type
  → [LLM extractor] — dates, events, people, doc reference → JSON
  → [Deduplication engine] — resolve overlapping/near-duplicate events
  → [Chronological sorter] — sort by extracted date
  → [Timeline API] — serve structured events to frontend
  → [Timeline UI] — interactive filterable/searchable timeline
  → [Export service] — Word / PDF generation for filing
```

## Implementation Steps

### Step 1: Project Scaffolding
- [ ] Initialize the project repository structure (backend, frontend, shared types).
- [ ] Set up language & framework (e.g., Python/FastAPI backend, React/TypeScript frontend).
- [ ] Configure linting, formatting, and CI checks.
- [ ] Create Docker Compose file for local dev (app, DB, OCR service, vector store placeholder).

### Step 2: Document Ingestion Service
- [ ] Design the data model for `Document`, `Matter`, and `Event` entities.
- [ ] Implement REST API endpoint `POST /api/matters` — create a new matter (case).
- [ ] Implement `POST /api/matters/{id}/documents` — upload one or more files.
- [ ] Implement `GET /api/matters/{id}/documents` — list documents in a matter.
- [ ] Store uploaded files in object storage (local filesystem or S3-compatible).
- [ ] Write integration tests for upload + listing.

### Step 3: OCR Pipeline
- [ ] Set up Tesseract OCR wrapper (or GPT-4V fallback for complex scans).
- [ ] Implement `POST /api/matters/{id}/documents/{docId}/process` — trigger OCR on scanned images.
- [ ] Extract and store raw text alongside the original file.
- [ ] Handle edge cases: password-protected PDFs, corrupted images, multi-page TIFF.
- [ ] Write tests with sample scanned documents.

### Step 4: Document Chunking & Classification
- [ ] Build text splitter that segments documents into manageable chunks (by page, section, or token limit).
- [ ] Implement document type classifier (prompt + LLM call or lightweight ML model).
- [ ] Classify each chunk with metadata: `docType`, `pageRange`, `summary`.
- [ ] Store chunks in a structured document store (PostgreSQL JSONB or a document DB).
- [ ] Write tests for chunking edge cases (very short docs, very long docs, mixed content).

### Step 5: LLM Event Extraction
- [ ] Design the extraction prompt template for consistent JSON output (dates, events, people, doc reference, confidence).
- [ ] Implement extraction service that calls an LLM (OpenAI / Anthropic / local) for each chunk.
- [ ] Parse and validate the structured JSON output against the `Event` schema.
- [ ] Handle retries and fallbacks if the LLM returns malformed output.
- [ ] Store extracted events linked to their source document + chunk.
- [ ] Write tests with known documents to validate extraction correctness.

### Step 6: Deduplication & Chronological Sorting
- [ ] Implement deduplication logic: fuzzy date matching, overlapping event descriptions, same person references.
- [ ] Sort events chronologically (handle partial dates, date ranges, approximate dates).
- [ ] Build API endpoint `GET /api/matters/{id}/timeline` — return sorted, deduplicated events.
- [ ] Add filtering capability: by date range, person, document type.
- [ ] Write tests for deduplication edge cases (same event from different sources, slightly different wording).

### Step 7: Interactive Timeline UI
- [ ] Set up React/TypeScript frontend with routing (matter list → matter detail → timeline).
- [ ] Implement matter list page: create new matter, select existing.
- [ ] Implement document upload UI: drag-and-drop, progress indicator.
- [ ] Build timeline component: horizontal scrollable timeline with event cards.
- [ ] Add filters: date range picker, person search, document type dropdown.
- [ ] Add search: full-text search across event descriptions.
- [ ] Show source document links for each event (jump to original doc).
- [ ] Write component tests and a manual QA script.

### Step 8: Export Service
- [ ] Implement Word document generation (python-docx or similar) from timeline data.
- [ ] Implement PDF generation (WeasyPrint / Puppeteer) from timeline data.
- [ ] Add export options to the timeline UI (buttons: "Export to Word", "Export to PDF").
- [ ] Style exports with a professional legal format (header, footer, page numbers, disclaimers).
- [ ] Write tests verifying generated file structure and content.

### Step 9: Integration & Polish
- [ ] Wire end-to-end flow: upload → process → timeline → export.
- [ ] Add error handling and user-friendly error messages throughout.
- [ ] Add loading states and progress tracking for long-running operations (OCR, LLM extraction).
- [ ] Write end-to-end tests covering the full happy path.
- [ ] Performance test with a realistic document set (hundreds of pages).

---

## Files to Modify (anticipated)

- `backend/` — new FastAPI/Python project directory
- `backend/app/main.py` — application entry point
- `backend/app/models/` — SQLAlchemy/Pydantic models
- `backend/app/routers/` — API route handlers
- `backend/app/services/` — business logic (OCR, extraction, deduplication)
- `frontend/` — new React/TypeScript project directory
- `frontend/src/pages/` — page components
- `frontend/src/components/` — UI components (timeline, uploader)
- `docker-compose.yml` — local development services

## Functional Components

| Function / Component | Location (anticipated) | Role |
|----------------------|------------------------|------|
| `MatterService` | `backend/app/services/matter.py` | CRUD for legal matters |
| `DocumentService` | `backend/app/services/document.py` | Upload, store, list documents |
| `OCRService` | `backend/app/services/ocr.py` | Extract text from scanned images |
| `ChunkingService` | `backend/app/services/chunker.py` | Split text into processable chunks |
| `ClassifierService` | `backend/app/services/classifier.py` | Classify chunks by document type |
| `ExtractionService` | `backend/app/services/extractor.py` | LLM-based event extraction |
| `DedupService` | `backend/app/services/dedup.py` | Deduplicate and sort events |
| `TimelineService` | `backend/app/services/timeline.py` | Build timeline API response |
| `TimelineView` | `frontend/src/components/TimelineView.tsx` | Interactive timeline UI |
| `ExportService` | `backend/app/services/export.py` | Generate Word/PDF exports |

## Data Model

### Matter
```
{
  id: UUID,
  title: string,
  description: string,
  created_at: datetime,
  updated_at: datetime,
  status: "active" | "archived"
}
```

### Document
```
{
  id: UUID,
  matter_id: UUID,
  filename: string,
  original_type: "pdf" | "txt" | "email" | "image",
  storage_path: string,
  ocr_text?: string,
  extracted_text?: string,
  doc_type?: "contract" | "email" | "police_report" | "medical_record" | "correspondence" | "other",
  uploaded_at: datetime,
  processing_status: "pending" | "ocr_done" | "classified" | "extracted" | "failed"
}
```

### Event
```
{
  id: UUID,
  matter_id: UUID,
  source_document_id: UUID,
  source_chunk_index: number,
  date: string,               // ISO 8601 or partial date
  date_precision: "exact" | "month" | "year" | "range",
  date_end?: string,          // for date ranges
  title: string,
  description: string,
  people: string[],
  doc_reference: string,      // page / paragraph reference
  confidence: number,         // 0.0 - 1.0
  dedup_group?: string        // hash for deduplication
}
```

## Boundaries

| Boundary | Input | Output |
|----------|-------|--------|
| Upload API | `multipart/form-data` (files + matter metadata) | `201 Created` + Document metadata |
| OCR Service | Image bytes or PDF stream | Extracted plain text |
| LLM Extraction | Text chunk + doc type label | Structured JSON array of Events |
| Timeline API | Matter ID + optional filters | Sorted, deduplicated Event array |
| Export API | Matter ID + format (`docx`/`pdf`) | Binary file stream |

## Considerations

- **LLM costs**: Extraction per chunk can be expensive. Cache results; allow users to review/edit before finalizing.
- **Date ambiguity**: Legal docs often have partial or relative dates ("on or about March 2024", "within 30 days of signing"). The extraction prompt should capture precision metadata.
- **PII**: Legal documents contain sensitive personal data. Ensure no data leaks to LLM providers without appropriate agreements.
- **Large matters**: A single case can have thousands of pages. Design chunking and extraction to run asynchronously with progress tracking.
- **Multi-language**: Legal cases may involve documents in multiple languages. Account for OCR and LLM language support.
- **Export formatting**: Courts have strict formatting requirements. Make export templates configurable per jurisdiction.
