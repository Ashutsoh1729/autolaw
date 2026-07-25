# Project Context: AI Legal Prep Assistant

## Source
Brainstorming session on Jul 25, 2026. Original whiteboard at `docs/notes/whiteboard.md`.

## Problem Statement
Lawyers spend 70% of their day on repetitive, non-judgment tasks (document organization, timeline creation, contract review). This app aims to automate the **case preparation phase** — the grunt work common across all case types.

## Top 5 Repetitive Legal Tasks (candidates to automate)

1. **Document Review & Redlining** — Reading contracts against templates, spotting risks, clause comparison.
2. **Legal Research** — Finding relevant precedents, statutes, case law across jurisdictions.
3. **First-Draft Generation** — Routine letters, motions, contracts from predictable patterns.
4. **Chronology Building** — Manually extracting dates/facts from hundreds of docs into a timeline.
5. **Client Intake** — Gathering scattered emails/attachments/meeting notes into a structured case file.

## Chosen Scope: Tasks #5 + #4 → then #2

Start with Intake (#5) and Chronology Builder (#4) as the core pipeline. Add Legal Research (#2) as the next module.

## Planned App Flow

```
Lawyer uploads/emails case docs (PDF, TXT, email, scan)
  → #5 Intake: Aggregate & structure docs into organized matter
  → #4 Chronology: Extract dates/events → build interactive timeline
  → #2 Legal Research: RAG over case law corpus → retrieve relevant precedents
  → Output: Timeline + research brief ready for lawyer review
```

## Where Chronology Builder Fits in the Workflow

**Before**: Lawyer gets a new case → client intake (gathers emails, contracts, police reports, medical records, correspondence) → all docs dumped in a folder.

**The task**: Read every document, extract every date/event/person, build a master timeline. Pure grunt work — no legal judgment needed.

**After**: Timeline becomes backbone of case narrative. Lawyer spots gaps, identifies key witnesses, prepares briefs.

**Who does it**: Junior associates or paralegals. Takes days to weeks per case.

## Input → Output Flow (Technical)

```
Raw docs (PDFs, emails, scans)
  → OCR (if scanned)
  → Chunk & classify by doc type
  → LLM extraction: dates, events, people, doc reference
  → Deduplicate & sort chronologically
  → Interactive timeline UI (filterable, searchable)
  → Export to Word/PDF for filing
```

## Gen AI Concepts Practiced

- Document parsing (unstructured → structured)
- OCR pipeline (Tesseract / GPT-4V)
- Prompt engineering for consistent date/event extraction
- JSON structured output from LLMs
- Entity resolution / deduplication
- RAG for legal research module

## Full Case Lifecycle (for context — NOT in scope)

After the prep phase, a lawyer goes through:

1. **Drafting** case documents (plaint, written statement, affidavits) based on facts + research
2. **Filing** with the court
3. **Evidence exchange** with opposing counsel
4. **Oral arguments** before the judge
5. **Responding** to court queries or opposing arguments
6. **Appealing** if needed

Different case types (civil, criminal, family, corporate, tax) have different procedural codes, filing requirements, and timelines — but the prep phase (intake + chronology + research) is common across all of them.

## Scope Decision

**What we're building**: A **Case Prep Assistant** — the intake → chronology → research pipeline that handles the 70% grunt work before a lawyer ever starts drafting or arguing.

**What we're NOT building**: Drafting, filing, evidence exchange, oral arguments, appeals. Those are downstream and out of scope for this project.

This keeps the portfolio project focused, coherent, and demonstrable without needing to replicate the entire legal profession. Solving the prep phase well is independently valuable.
