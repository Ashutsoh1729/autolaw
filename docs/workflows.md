# AutoLaw Phase 1 — Workflow Diagrams

> **Phase 1: Intake + Chronology Builder**
> These diagrams document every workflow in the system, showing how data flows
> through frontend pages, API routes, backend services, database models, and
> external services.

---

## Table of Contents

1. [Component Map — All Parts of the System](#1-component-map--all-parts-of-the-system)
2. [Matter Lifecycle](#2-matter-lifecycle)
3. [Document Ingestion](#3-document-ingestion)
4. [Document Processing Pipeline](#4-document-processing-pipeline)
5. [Timeline Browsing](#5-timeline-browsing)
6. [Timeline Export](#6-timeline-export)
7. [Email Ingestion Setup](#7-email-ingestion-setup)
8. [Health Check](#8-health-check)
9. [Full System Architecture](#9-full-system-architecture)

---

## 1. Component Map — All Parts of the System

```mermaid
graph TB
    subgraph Frontend["Frontend (Vite + React + TypeScript)"]
        direction TB
        P1["/dashboard<br/>Dashboard.tsx"]
        P2["/matters/new<br/>CreateMatter.tsx"]
        P3["/matters/:id<br/>MatterDetail.tsx"]
        P4["/matters/:id/timeline<br/>TimelineView.tsx"]

        subgraph Components["Shared Components"]
            C1["Navbar.tsx"]
            C2["DropZone.tsx"]
            C3["ProcessingBadge.tsx"]
            C4["ProgressBar.tsx"]
            C5["EmailForwardingSetup.tsx"]
        end

        subgraph Hooks["Custom Hooks"]
            H1["useMatter.ts"]
            H2["useUpload.ts"]
        end

        subgraph UI["UI Primitives (shadcn-style)"]
            U1["Button / Input / Label"]
            U2["Card / Badge / Progress"]
            U3["Select / Dialog / Textarea"]
        end
    end

    subgraph Backend["Backend (FastAPI + SQLAlchemy)"]
        direction TB

        subgraph Routers["API Routers"]
            R1["matters.py<br/>/api/matters"]
            R2["documents.py<br/>/api/matters/{id}/documents"]
            R3["timeline.py<br/>/api/matters/{id}/timeline"]
            R4["export.py<br/>/api/matters/{id}/export"]
        end

        subgraph Services["Services"]
            S1["matter.py<br/>Matter CRUD"]
            S2["document.py<br/>Upload & Validation"]
            S3["ocr.py<br/>Tesseract + PyPDF"]
            S4["chunker.py<br/>Text Splitting"]
            S5["classifier.py<br/>Doc Type Classification"]
            S6["extractor.py<br/>LLM Event Extraction"]
            S7["dedup.py<br/>Fuzzy Dedup + Sort"]
            S8["timeline.py<br/>Timeline Queries"]
            S9["export.py<br/>Word / PDF Generation"]
        end

        subgraph Models["Database Models"]
            M1["Matter<br/>(case metadata)"]
            M2["Document<br/>(file metadata + text)"]
            M3["Event<br/>(extracted timeline events)"]
        end

        subgraph Storage["File Storage"]
            ST1["LocalStorageProvider<br/>backend/uploads/"]
        end
    end

    subgraph External["External Services"]
        E1["Tesseract OCR<br/>(system binary)"]
        E2["OpenAI API 🔑"]
        E3["Anthropic API 🔑"]
    end
```

---

## 2. Matter Lifecycle

Create, view, update, archive, and delete legal matters.

### Flow

```mermaid
flowchart LR
    subgraph User["👤 User Actions"]
        A1["Click '+ New Matter'"]
        A2["Fill form + optionally<br/>upload files"]
        A3["Click 'Create'"]
        A4["View matter detail"]
        A5["Edit / Archive matter"]
    end

    subgraph Frontend["🖥 Frontend Pages"]
        F1["📄 Dashboard"]
        F2["📄 Create Matter"]
        F3["📄 Matter Detail"]
    end

    subgraph API["🌐 API Routes"]
        B1["POST /api/matters"]
        B2["GET /api/matters/{id}"]
        B3["PATCH /api/matters/{id}"]
        B4["DELETE /api/matters/{id}"]
        B5["GET /api/matters"]
    end

    subgraph Services["⚙ Services"]
        S1["📋 matter.py<br/>create_matter()"]
        S2["📋 matter.py<br/>get_matter()"]
        S3["📋 matter.py<br/>update_matter()"]
        S4["📋 matter.py<br/>delete_matter()"]
        S5["📋 matter.py<br/>list_matters()"]
    end

    subgraph DB["🗄 Database"]
        D1["(ML) Matter table"]
    end

    subgraph Storage["💾 File Storage"]
        ST1["🗂 Matter directory<br/>backend/uploads/matters/{id}/"]
    end

    A1 --> F1
    F1 -->|navigate| F2
    A2 --> F2
    A3 --> F2
    F2 --> B1
    B1 --> S1
    S1 --> D1
    S1 -->|generate unique<br/>email address| D1
    B1 -->|redirect| F3

    F3 --> B2
    B2 --> S2
    S2 --> D1

    F3 -->|user edits| B3
    B3 --> S3
    S3 --> D1

    F3 -->|user archives| B3
    B3 --> S3
    S3 --> D1

    F3 -->|user deletes| B4
    B4 --> S4
    S4 --> D1
    S4 --> ST1

    F1 --> B5
    B5 --> S5
    S5 --> D1
```

### Entry Points

| Action | URL | Method | Frontend |
|---|---|---|---|
| List all matters | `/dashboard` | `GET /api/matters` | `Dashboard.tsx` |
| Create new matter | `/matters/new` | `POST /api/matters` | `CreateMatter.tsx` |
| View matter detail | `/matters/:id` | `GET /api/matters/{id}` | `MatterDetail.tsx` |
| Update matter | — | `PATCH /api/matters/{id}` | `MatterDetail.tsx` |
| Delete matter | — | `DELETE /api/matters/{id}` | `MatterDetail.tsx` |

### Data Model (Matter)

```
id:         UUID string (PK)
title:      string (required)
case_number: string (optional)
case_type:  "Civil" | "Criminal" | "Family" | ...
jurisdiction: string (optional)
description: text (optional)
status:     "active" | "archived"
email_address: string (auto-generated)
created_at: datetime
updated_at: datetime
```

---

## 3. Document Ingestion

Upload, validate, store, and list documents within a matter.

### Flow

```mermaid
flowchart LR
    subgraph User["👤 User Actions"]
        A1["Select files<br/>via drag-and-drop<br/>or file browser"]
        A2["Click 'Upload'"]
        A3["Monitor per-file<br/>progress bars"]
        A4["Refresh document list"]
    end

    subgraph Frontend["🖥 Frontend"]
        F1["🔄 DropZone.tsx<br/>File validation<br/>(type + size)"]
        F2["🔄 useUpload.ts<br/>XHR upload with<br/>progress tracking"]
        F3["🔄 UploadProgressBar"]
        F4["📄 MatterDetail.tsx<br/>Document list"]
    end

    subgraph Validation["✅ Validation Layer"]
        V1["File extension check<br/>(.pdf .txt .eml .png .jpg .tiff)"]
        V2["File size check<br/>(max 50 MB per file)"]
        V3["Matter total quota<br/>(max 500 MB)"]
        V4["Duplicate filename<br/>check"]
    end

    subgraph API["🌐 API Routes"]
        B1["POST /matters/{id}/documents"]
        B2["GET /matters/{id}/documents"]
        B3["GET /matters/{id}/documents/{docId}"]
    end

    subgraph Services["⚙ Services"]
        S1["📋 document.py<br/>upload_document()"]
        S2["📋 document.py<br/>list_documents()"]
    end

    subgraph DB["🗄 Database"]
        D2["(DL) Document table"]
    end

    subgraph Storage["💾 File Storage"]
        ST1["🗂 LocalStorageProvider<br/>backend/uploads/matters/{id}/"]
    end

    A1 --> F1
    F1 -->|valid files| F2
    F1 -->|invalid| A1
    A2 --> F2

    F2 -->|XHR POST| B1
    B1 --> V1
    B1 --> V2
    B1 --> V3
    B1 --> V4
    B1 --> S1
    S1 --> ST1
    ST1 -->|storage_path| S1
    S1 -->|create record| D2
    B1 -->|response| F3
    F3 -->|progress| A3

    A4 --> F4
    F4 --> B2
    B2 --> S2
    S2 --> D2

    F4 --> B3
    B3 --> S2
    S2 --> D2
```

### File Type Validation

| Extension | `original_type` | Allowed |
|---|---|---|
| `.pdf` | `pdf` | ✅ |
| `.txt` | `txt` | ✅ |
| `.eml` | `email` | ✅ |
| `.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`, `.bmp` | `image` | ✅ |
| Everything else | — | ❌ (400 error) |

### Data Model (Document)

```
id:                UUID string (PK)
matter_id:         UUID string (FK → matters.id)
filename:          string
original_type:     "pdf" | "txt" | "email" | "image"
storage_path:      string (relative to uploads/)
file_size_bytes:   integer
ocr_text:          text (nullable, populated by OCR)
extracted_text:    text (nullable, populated after process)
doc_type:          "contract" | "email" | "police_report" | "medical_record" |
                   "correspondence" | "other" (nullable)
processing_status: "pending" | "uploading" | "ocr_pending" | "ocr_done" |
                   "classifying" | "classified" | "extracting" | "extracted" |
                   "failed"
processing_error:  text (nullable)
page_count:        integer (nullable)
uploaded_at:       datetime
```

---

## 4. Document Processing Pipeline

The core Gen AI pipeline: OCR → Chunk → Classify → Extract → Deduplicate → Store.

Triggered by `POST /api/matters/{id}/documents/{docId}/process`.

```mermaid
flowchart TB
    subgraph Trigger["🚀 Entry Point"]
        T["User clicks 'Process'<br/>or API call<br/>POST .../documents/{docId}/process"]
    end

    subgraph Router["🌐 documents.py"]
        R["process_document_endpoint()"]
    end

    subgraph Pipeline["⚙ Processing Pipeline"]
        direction TB

        Step0["1️⃣ Read stored file<br/>storage_provider.read()"]
        Step1["2️⃣ OCR / Text Extraction<br/>ocr.py: extract_text()"]
        Step2["3️⃣ Page Counting<br/>ocr.py: count_pages()"]
        Step3["4️⃣ Text Chunking<br/>chunker.py: chunk_document()"]
        Step4["5️⃣ Document Classification<br/>classifier.py: classify_document()"]
        Step5["6️⃣ Event Extraction<br/>(per chunk)<br/>extractor.py: extract_events_from_chunk()"]
        Step6["7️⃣ Process Events<br/>(add metadata + dedup groups)<br/>dedup.py: process_events()"]
        Step7["8️⃣ Store Events in DB<br/>Event model → database"]
    end

    subgraph Decisions["🔀 Decision Points"]
        D1{"Has meaningful<br/>text?"}
        D2{"LLM configured?<br/>(API key present)"}
    end

    subgraph External["🔧 External Services"]
        E1["PyPDF<br/>Fast text extract"]
        E2["Tesseract OCR<br/>(fallback for scanned PDFs)"]
        E3["Tesseract OCR<br/>Image text extraction"]
        E4["OpenAI / Anthropic API<br/>(if configured)"]
    end

    subgraph DB["🗄 Database"]
        D["(DL) Document record<br/>updated in-place"]
        E["(EL) Event records<br/>created"]
    end

    subgraph Response["📤 Response"]
        Resp["{ status, message,<br/>event_count, chunk_count }"]
    end

    T --> R
    R --> Step0
    Step0 --> Step1

    Step1 --> D1
    D1 -->|"No text (empty doc)"| E["(DL) Document.status = 'failed'<br/>error = 'No text extracted'"]
    D1 -->|"Has text"| Step2

    Step2 --> Step3

    Step3 --> Step4

    Step4 --> Step5

    Step5 --> D2
    D2 -->|"Yes"| E4
    D2 -->|"No"| Fallback["Pattern-based extractor<br/>(date regex fallback)"]
    E4 --> Step6
    Fallback --> Step6

    Step6 --> Step7
    Step7 --> E

    E -->|update status = 'extracted'| D
    D --> Resp
```

### Extraction Detail

```mermaid
flowchart LR
    subgraph Chunks["Each Chunk"]
        CH["Text Chunk<br/>(index, text,<br/>page range)"]
    end

    subgraph Extractor["LLM Extraction"]
        direction TB
        IN["Build prompt from<br/>template + chunk text"]
        LLMCall["Call LLM<br/>(OpenAI / Anthropic)"]
        JSONParse["Parse JSON response<br/>(with fallbacks)"]
        Validate["Validate against<br/>Event schema"]
    end

    subgraph PatternFallback["Pattern Fallback<br/>(no API key)"]
        PF["Regex date matching<br/>+ context extraction<br/>→ low confidence events"]
    end

    CH --> IN
    IN --> LLMCall
    LLMCall --> JSONParse
    JSONParse --> Validate

    CH --> PF

    Validate --> Events["Structured events[]"]
    PF --> Events
```

### Processing Status Progression

```
pending → ocr_pending → ocr_done → classifying → extracting → extracted
                                                                   ↓
                                                               (on error) failed
```

### Event Data Model

```
id:                  UUID string (PK)
matter_id:           UUID string (FK → matters.id)
source_document_id:  UUID string (FK → documents.id)
source_chunk_index:  integer (nullable)
date:                string (ISO 8601 or partial)
date_precision:      "exact" | "month" | "year" | "range"
date_end:            string (nullable, for date ranges)
title:               string
description:         text (nullable)
people:              text (JSON array, nullable)
doc_reference:       string (page/para ref, nullable)
confidence:          float (0.0–1.0)
dedup_group:         string (hash for dedup, nullable)
created_at:          datetime
```

---

## 5. Timeline Browsing

View, filter, and explore extracted events in a chronological timeline.

### Flow

```mermaid
flowchart LR
    subgraph User["👤 User Actions"]
        A1["Click 'Timeline'<br/>button on matter detail"]
        A2["Apply filters<br/>(date range, person,<br/>full-text search)"]
        A3["Click event card<br/>to expand details"]
        A4["View confidence bar,<br/>people, source doc"]
    end

    subgraph Frontend["🖥 Frontend Pages"]
        F1["📄 MatterDetail.tsx"]
        F2["📄 TimelineView.tsx"]
        F3["🔍 Filter bar<br/>(search, date, person)"]
        F4["📇 Event cards<br/>(expandable)"]
    end

    subgraph API["🌐 API Routes"]
        B1["GET /matters/{id}/timeline<br/>?search=...<br/>&date_from=...<br/>&date_to=...<br/>&person=..."]
    end

    subgraph Services["⚙ Services"]
        S1["📋 timeline.py<br/>get_timeline_events()"]
        S2["📋 matter.py<br/>get_matter()"]
    end

    subgraph DB["🗄 Database"]
        D1["(ML) Matter table"]
        D2["(DL) Document table<br/>(for source filename)"]
        D3["(EL) Event table"]
    end

    A1 --> F1
    F1 -->|navigate| F2

    F2 --> B1
    B1 --> S1
    S1 --> D3
    S1 -->|join doc names| D2
    S1 -->|verify matter exists| D2

    A2 --> F3
    F3 -->|re-fetch| B1

    A3 --> F4
    F4 -->|show people, source,<br/>confidence| A4
```

### Filter Parameters

| Parameter | Location | Effect |
|---|---|---|
| `search` | Query string | Full-text search on `title` and `description` |
| `date_from` | Query string | Filter events on or after this date (ISO 8601) |
| `date_to` | Query string | Filter events on or before this date (ISO 8601) |
| `person` | Query string | Filter by person name (substring match on `people` JSON) |

### Timeline Visual Encoding

| Precision | Card Left-Border Color | Meaning |
|---|---|---|
| `exact` | Blue (primary) | Full date known |
| `month` | Light blue | Only month/year known |
| `year` | Yellow | Only year known |
| `range` | Purple | Event spans a date range |

---

## 6. Timeline Export

Export the filtered timeline to Word (.docx) or PDF.

### Flow

```mermaid
flowchart LR
    subgraph User["👤 User Actions"]
        A1["Click 'Export to Word'"]
        A2["Click 'Export to PDF'"]
        A3["Download generated file"]
    end

    subgraph Frontend["🖥 Frontend"]
        F1["📄 TimelineView.tsx<br/>Export buttons"]
        F2["🔄 exportTimeline()<br/>hook function"]
    end

    subgraph API["🌐 API Routes"]
        B1["GET /matters/{id}/export?format=docx"]
        B2["GET /matters/{id}/export?format=pdf"]
    end

    subgraph Services["⚙ Services"]
        S1["📋 timeline.py<br/>get_timeline_events()"]
        S2["📊 export.py<br/>export_to_docx()"]
        S3["📊 export.py<br/>export_to_pdf()"]
    end

    subgraph Generators["📄 Document Generation"]
        G1["🐍 python-docx<br/>Timeline table<br/>Legal formatting<br/>(Times New Roman,<br/>margins, headers)"]
        G2["🐍 fpdf2<br/>Page breaks<br/>Professional layout<br/>(same content)"]
    end

    subgraph Output["📥 Output"]
        O1["📎 timeline_{id}.docx"]
        O2["📎 timeline_{id}.pdf"]
    end

    A1 --> F1
    A2 --> F1
    F1 --> F2
    F2 -->|format=docx| B1
    F2 -->|format=pdf| B2

    B1 --> S1
    B2 --> S1
    S1 -->|fetch events| DB[("🗄 DB")]

    B1 --> S2
    S2 --> G1
    G1 --> O1
    O1 -->|download| A3

    B2 --> S3
    S3 --> G2
    G2 --> O2
    O2 -->|download| A3

    subgraph ExportFormat["Export Document Structure"]
        T["📄 Document"]
        H["─ Header: 'Chronology of Events'"]
        M["─ Matter title + generation date"]
        L["─ Separator line"]
        L1["1️⃣ 2024-01-15"]
        D1["  Event title"]
        D1D["  Description"]
        P1["  People involved"]
        S1R["  Source: contract.pdf · Conf: 95%"]
        L2["  2️⃣ 2024-03-20"]
        D2["  ..."]
        F["─ Footer disclaimer"]
    end
```

### Error Handling

| Scenario | Response |
|---|---|
| Matter not found | `404` — "Matter not found" |
| No events to export | `404` — "No timeline events found. Process documents first." |
| Unsupported format | `400` — "Unsupported format. Use 'docx' or 'pdf'." |

---

## 7. Email Ingestion Setup

Configure email forwarding so case-related emails are auto-attached to a matter.

### Flow

```mermaid
flowchart LR
    subgraph User["👤 User Actions"]
        A1["View matter detail"]
        A2["Copy email address"]
        A3["Forward case emails<br/>from personal email<br/>to the matter address"]
    end

    subgraph Frontend["🖥 Frontend"]
        F1["📄 MatterDetail.tsx"]
        F2["📧 EmailForwardingSetup.tsx<br/>- Display unique address<br/>- Copy button<br/>- Usage instructions"]
    end

    subgraph Backend["⚙ Backend"]
        B1["Matter creation<br/>generates unique address"]
        B2["matter.email_address =<br/>'{hash}@matter.autolaw.app'"]
    end

    subgraph DB["🗄 Database"]
        D1["(ML) Matter.email_address"]
    end

    A1 --> F1
    F1 --> F2
    F2 -->|displays| D1
    A2 -->|click copy| F2
    A3 -->|📨 forwarded emails| Future["(Phase 2: Email listener<br/>service not yet built)"]

    B1 -->|on create| B2
    B2 --> D1
```

### Current Status

The email address is **generated and stored** during matter creation. The
email listener service (IMAP/POP3 polling, inbound webhook) is **planned for
Phase 2**. For now, the UI shows the address and setup instructions so users
can start forwarding emails — they'll be processed when the listener is built.

---

## 8. Health Check

Simple liveness probe for the backend.

```mermaid
flowchart LR
    A["🧪 External monitor<br/>or developer"] -->|"GET /api/health"| B["🌐 FastAPI router"]
    B -->|"Response"| C["{ status: 'ok',<br/>  version: '0.1.0' }"]
```

---

## 9. Full System Architecture

End-to-end view of all components, data stores, and external services.

```mermaid
graph TB
    subgraph Browser["🌐 Browser"]
        React["React SPA<br/>(Vite dev server :5173)"]
    end

    subgraph FastAPI["🚀 FastAPI Backend (:8000)"]
        direction TB

        MW["CORS Middleware"]
        RouterLayer["Routers<br/>matters / documents<br/>timeline / export"]

        subgraph ServiceLayer["Service Layer"]
            MatterSvc["Matter Service"]
            DocSvc["Document Service<br/>+ Validation"]
            OCRSvc["OCR Service"]
            ChunkerSvc["Chunking Service"]
            ClassifierSvc["Classification Service"]
            ExtractorSvc["Extraction Service"]
            DedupSvc["Dedup Service"]
            TimelineSvc["Timeline Service"]
            ExportSvc["Export Service"]
        end

        Storage["Storage Provider<br/>(LocalStorageProvider)"]
    end

    subgraph Data["🗄 Data Stores"]
        DB[("SQLite DB<br/>autolaw.db")]
        FS[("Filesystem<br/>uploads/")]
    end

    subgraph External["🔧 External Dependencies"]
        Tesseract["Tesseract OCR<br/>(system binary)"]
        OpenAI["OpenAI API"]
        Anthropic["Anthropic API"]
    end

    subgraph Deploy["🐳 Docker Compose"]
        Postgres["PostgreSQL 16<br/>(production target)"]
    end

    React -->|HTTP /api/*| MW
    MW --> RouterLayer

    RouterLayer --> MatterSvc
    RouterLayer --> DocSvc
    RouterLayer --> TimelineSvc
    RouterLayer --> ExportSvc

    DocSvc --> Storage
    Storage --> FS

    MatterSvc --> DB
    DocSvc --> DB
    TimelineSvc --> DB

    DocSvc --> OCRSvc
    OCRSvc --> Tesseract
    OCRSvc -->|via PyPDF + pdf2image| FS

    OCRSvc --> ChunkerSvc
    ChunkerSvc --> ClassifierSvc
    ClassifierSvc --> ExtractorSvc
    ExtractorSvc -->|if configured| OpenAI
    ExtractorSvc -->|if configured| Anthropic
    ExtractorSvc --> DedupSvc
    DedupSvc --> DB

    ExportSvc --> TimelineSvc

    Note["📝 SQLite used now;<br/>PostgreSQL ready for production<br/>(swap DATABASE_URL)"]
    DB --- Note
```

---

## Index of All API Endpoints

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/health` | Health check | — | `{status, version}` |
| `POST` | `/api/matters` | Create matter | `{title, case_number?, case_type?, ...}` | `MatterResponse` (201) |
| `GET` | `/api/matters` | List matters | `?search=&status=&skip=&limit=` | `{matters[], total}` |
| `GET` | `/api/matters/{id}` | Get matter | — | `MatterResponse` |
| `PATCH` | `/api/matters/{id}` | Update matter | `{title?, status?, ...}` | `MatterResponse` |
| `DELETE` | `/api/matters/{id}` | Delete matter | — | 204 No Content |
| `POST` | `/api/matters/{id}/documents` | Upload files | `multipart files[]` | `DocumentResponse[]` (201) |
| `GET` | `/api/matters/{id}/documents` | List documents | `?skip=&limit=` | `{documents[], total}` |
| `GET` | `/api/matters/{id}/documents/{docId}` | Get document | — | `DocumentResponse` |
| `POST` | `/api/matters/{id}/documents/{docId}/process` | Process document | — | `{status, message, ...}` |
| `GET` | `/api/matters/{id}/timeline` | Get timeline | `?search=&date_from=&date_to=&person=` | `{events[], total_events}` |
| `GET` | `/api/matters/{id}/export` | Export timeline | `?format=docx\|pdf` | Binary file download |

## Index of All Frontend Routes

| Path | Page Component | Description |
|---|---|---|
| `/` | Redirect → `/dashboard` | Root redirect |
| `/dashboard` | `Dashboard.tsx` | Matter cards, search, filter, "New Matter" CTA |
| `/matters/new` | `CreateMatter.tsx` | Case metadata form + drag-and-drop upload |
| `/matters/:id` | `MatterDetail.tsx` | Document list, status badges, upload more, process, email setup |
| `/matters/:id/timeline` | `TimelineView.tsx` | Interactive timeline with filters and export |

## Index of All Database Models

| Model | Table | Key Fields | Relationships |
|---|---|---|---|
| `Matter` | `matters` | `id`, `title`, `status`, `email_address` | → `documents[]`, → `events[]` |
| `Document` | `documents` | `id`, `matter_id` (FK), `filename`, `processing_status`, `storage_path` | → `matter`, → `events[]` |
| `Event` | `events` | `id`, `matter_id` (FK), `source_document_id` (FK), `date`, `title`, `people` | → `matter`, → `source_document` |

---

> **Generated for Phase 1 completion review.**
> Workflows 1–8 are fully implemented. Email ingestion (workflow 7) has the
> setup UI and data model complete; the background email listener is deferred
> to Phase 2.
