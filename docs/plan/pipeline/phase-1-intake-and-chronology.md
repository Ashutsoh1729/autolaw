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

## Frontend Input Flow

### UI Screens / Pages

```
┌─────────────────────────────────────────────────────────┐
│  Dashboard (/dashboard)                                  │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  My Matters                    [+ New Matter]       │ │
│  │  ┌──────┐ ┌──────┐ ┌──────┐                        │ │
│  │  │Smith │ │Jones │ │Doe   │  ...                    │ │
│  │  │ v.   │ │ v.   │ │ v.   │                        │ │
│  │  │Corp  │ │State │ │City  │                        │ │
│  │  └──────┘ └──────┘ └──────┘                        │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Create Matter (/matters/new)                            │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Case Title     [____________________________]      │ │
│  │  Case Number    [____________________________]      │ │
│  │  Case Type      [▼ Civil / Criminal / Family / ...] │ │
│  │  Jurisdiction   [____________________________]      │ │
│  │  Description    [____________________________]      │ │
│  │  ┌─────────────────────────────────────────────────┐│ │
│  │  │  Drag & drop files here, or click to browse     ││ │
│  │  │  Supported: PDF, TXT, EML, PNG, JPG, TIFF       ││ │
│  │  └─────────────────────────────────────────────────┘│ │
│  │  [Uploaded: smith_contract.pdf  ✓]  [×]             │ │
│  │  [Uploaded: police_report.pdf  ⬆ 60%]              │ │
│  │                                                      │ │
│  │  [Create Matter]                                     │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Matter Detail (/matters/:id)                            │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Smith v. Corporation                     [Timeline]│ │
│  │  ─────────────────────────────────────────────────── │ │
│  │  Documents (12)   [+ Add]  [Email Forwarding Setup] │ │
│  │  ┌─────────────────────────────────────────────────┐│ │
│  │  │ ○ contract.pdf          [Contract]     Done  ▼ ││ │
│  │  │ ○ police_report.pdf     [Police Rpt]   Processing│ │
│  │  │ ○ email.eml             [Email]        Queued   ││ │
│  │  │ ○ scan_001.png          [Other]        OCR     ││ │
│  │  │   ...                                        ││ │
│  │  └─────────────────────────────────────────────────┘│ │
│  │                                                     │ │
│  │  [Upload More Documents]  [Refresh Processing]      │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Timeline View (/matters/:id/timeline)                    │
│  ... (detailed in Step 8)                                │
└─────────────────────────────────────────────────────────┘
```

### User Flow

1. **Dashboard** → User sees list of existing matters. Clicks "[+ New Matter]".
2. **Create Matter** → User fills in case metadata (title, number, type, jurisdiction, description). Drags-and-drops or browses for documents. Sees per-file upload progress and validation feedback. Clicks "Create Matter".
3. **Matter Detail** → User lands on the matter detail page. Sees the document list with processing status per file. Can upload more documents, configure email forwarding, or navigate to the timeline.
4. **Timeline** → User views the extracted timeline (detailed in Step 8).
5. **Export** → User exports the timeline to Word or PDF.

### Input Validation

- **File type**: Accept only allowed extensions (`.pdf`, `.txt`, `.eml`, `.png`, `.jpg`, `.jpeg`, `.tiff`). Reject with inline error message.
- **File size**: Enforce a per-file limit (e.g., 50 MB) and a per-matter total limit. Show warning before upload starts.
- **Required fields**: Case title is mandatory. All other metadata fields optional but encouraged.
- **Duplicate detection**: Check filename against existing documents in the matter; prompt user to confirm if re-uploading.

### Progress Indicators

- **Per-file upload progress bar**: Shows upload percentage for each file during the upload phase.
- **Per-document processing badge**: Each document in the list shows its processing stage (`Queued`, `OCR`, `Classifying`, `Extracting`, `Done`, `Failed`).
- **Matter-level progress bar**: Aggregate progress across all documents (e.g., "6 of 12 documents processed").
- **Email ingestion status**: Separate section showing emails received, parsed, and linked to the matter.

---

## Implementation Steps

### Step 1: Project Scaffolding
- [x] Backend initialized — Python/FastAPI project already set up. No action needed.
- [x] Frontend stack decided: **Vite + React Router + TypeScript + shadcn/ui**.
- [ ] Scaffold frontend project with Vite + React + TypeScript template.
- [ ] Configure linting, formatting, and CI checks.
- [ ] Create Docker Compose file for local dev (app, DB, OCR service, vector store placeholder).

### Step 2: Document Ingestion Service
- [ ] Design the data model for `Document`, `Matter`, and `Event` entities.
- [ ] Implement REST API endpoint `POST /api/matters` — create a new matter (case).
- [ ] Implement `POST /api/matters/{id}/documents` — upload one or more files.
- [ ] Implement `GET /api/matters/{id}/documents` — list documents in a matter.
- [ ] Store uploaded files in object storage (local filesystem or S3-compatible).
- [ ] Write integration tests for upload + listing.

### Step 3: Frontend Input Screens
- [ ] Build the Dashboard page (`/dashboard`): list existing matters with search/filter, "+ New Matter" button.
- [ ] Build the Create Matter form (`/matters/new`): case metadata fields (title, number, type, jurisdiction, description).
- [ ] Implement drag-and-drop file upload zone with file-type and file-size validation.
- [ ] Add per-file upload progress indicator (XHR progress event or companion upload status endpoint).
- [ ] Build the Matter Detail page (`/matters/:id`): document list with processing status badges, "Upload More" button.
- [ ] Add inline error display and field-level validation feedback on the Create Matter form.
- [ ] Add duplicate filename detection during upload (prompt if re-uploading existing file).
- [ ] Implement email forwarding setup UI: display unique matter email address, instructions for forwarding.
- [ ] Build email ingestion status section on the Matter Detail page.
- [ ] Add a "Refresh Processing" button to recheck document processing status.
- [ ] Write component tests for each screen.

### Step 4: OCR Pipeline
- [ ] Set up Tesseract OCR wrapper (or GPT-4V fallback for complex scans).
- [ ] Implement `POST /api/matters/{id}/documents/{docId}/process` — trigger OCR on scanned images.
- [ ] Extract and store raw text alongside the original file.
- [ ] Handle edge cases: password-protected PDFs, corrupted images, multi-page TIFF.
- [ ] Write tests with sample scanned documents.

### Step 5: Document Chunking & Classification
- [ ] Build text splitter that segments documents into manageable chunks (by page, section, or token limit).
- [ ] Implement document type classifier (prompt + LLM call or lightweight ML model).
- [ ] Classify each chunk with metadata: `docType`, `pageRange`, `summary`.
- [ ] Store chunks in a structured document store (PostgreSQL JSONB or a document DB).
- [ ] Write tests for chunking edge cases (very short docs, very long docs, mixed content).

### Step 6: LLM Event Extraction
- [ ] Design the extraction prompt template for consistent JSON output (dates, events, people, doc reference, confidence).
- [ ] Implement extraction service that calls an LLM (OpenAI / Anthropic / local) for each chunk.
- [ ] Parse and validate the structured JSON output against the `Event` schema.
- [ ] Handle retries and fallbacks if the LLM returns malformed output.
- [ ] Store extracted events linked to their source document + chunk.
- [ ] Write tests with known documents to validate extraction correctness.

### Step 7: Deduplication & Chronological Sorting
- [ ] Implement deduplication logic: fuzzy date matching, overlapping event descriptions, same person references.
- [ ] Sort events chronologically (handle partial dates, date ranges, approximate dates).
- [ ] Build API endpoint `GET /api/matters/{id}/timeline` — return sorted, deduplicated events.
- [ ] Add filtering capability: by date range, person, document type.
- [ ] Write tests for deduplication edge cases (same event from different sources, slightly different wording).

### Step 8: Interactive Timeline UI
- [ ] Set up Vite + React Router frontend with routing (matter detail → timeline, matter list → detail).
- [ ] Build the Timeline View page (`/matters/:id/timeline`): horizontal scrollable timeline with event cards.
- [ ] Add timeline filters: date range picker, person search, document type dropdown.
- [ ] Add full-text search across event descriptions.
- [ ] Show source document links for each event (jump to original doc preview).
- [ ] Link export buttons in the timeline toolbar (reuse export API from Step 9).
- [ ] Add empty state: "No events extracted yet. Documents are still processing."
- [ ] Write component tests for the timeline view.

### Step 9: Export Service
- [ ] Implement Word document generation (python-docx or similar) from timeline data.
- [ ] Implement PDF generation (WeasyPrint / Puppeteer) from timeline data.
- [ ] Add export options to the timeline UI (buttons: "Export to Word", "Export to PDF").
- [ ] Style exports with a professional legal format (header, footer, page numbers, disclaimers).
- [ ] Write tests verifying generated file structure and content.

### Step 10: Integration & Polish
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
- `frontend/` — new Vite + React + TypeScript project directory
- `frontend/src/pages/Dashboard.tsx` — matter list / home page
- `frontend/src/pages/CreateMatter.tsx` — new matter form + document upload
- `frontend/src/pages/MatterDetail.tsx` — document list with status, upload more
- `frontend/src/pages/TimelineView.tsx` — timeline display
- `frontend/src/components/DropZone.tsx` — drag-and-drop file upload
- `frontend/src/components/ProcessingBadge.tsx` — per-document status badge
- `frontend/src/components/ProgressBar.tsx` — upload/processing progress
- `frontend/src/components/TimelineView.tsx` — interactive timeline component
- `frontend/src/hooks/` — custom React hooks (useUpload, useMatter, etc.)
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
| `ExportService` | `backend/app/services/export.py` | Generate Word/PDF exports |
| `Dashboard` | `frontend/src/pages/Dashboard.tsx` | Matter list page with search/filter + "New Matter" CTA |
| `CreateMatter` | `frontend/src/pages/CreateMatter.tsx` | Case metadata form + drag-and-drop file upload |
| `MatterDetail` | `frontend/src/pages/MatterDetail.tsx` | Document list with per-file processing status |
| `TimelineView` | `frontend/src/pages/TimelineView.tsx` | Full timeline page layout (wraps Timeline component) |
| `DropZone` | `frontend/src/components/DropZone.tsx` | Drag-and-drop zone with file-type/size validation |
| `ProcessingBadge` | `frontend/src/components/ProcessingBadge.tsx` | Badge showing Queued/OCR/Classifying/Extracting/Done/Failed |
| `ProgressBar` | `frontend/src/components/ProgressBar.tsx` | Per-file upload progress and aggregate matter progress |
| `TimelineComponent` | `frontend/src/components/TimelineComponent.tsx` | Interactive timeline with event cards, filters, search |
| `EmailForwardingSetup` | `frontend/src/components/EmailForwardingSetup.tsx` | Config panel for email ingestion (unique address, instructions) |
| `useUpload` | `frontend/src/hooks/useUpload.ts` | Custom hook: file upload with progress tracking |

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
| Dashboard → API | — | `GET /api/matters` → Matter[] |
| Create Matter (form → API) | Form fields + files (`multipart/form-data`) | `POST /api/matters` → Matter + Document[] |
| Document Upload (UI → API) | File(s) + Matter ID | `POST /api/matters/{id}/documents` → Document[] + per-file upload progress (XHR / WebSocket) |
| Matter Detail → API | Matter ID | `GET /api/matters/{id}` + `GET /api/matters/{id}/documents` → Matter + Document[] with processing status |
| Upload API (backend boundary) | `multipart/form-data` (files + matter metadata) | `201 Created` + Document metadata |
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
