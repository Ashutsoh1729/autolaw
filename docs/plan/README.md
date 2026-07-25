# Implementation Plans — AI Legal Prep Assistant

This directory contains structured implementation plans for the autolaw project.

## Currently Active Plans

> Reference the detailed plan before implementing a phase.

| Feature | Category | Plan File | Status |
|---------|----------|-----------|--------|
| Phase 1 — Intake + Chronology Builder | `pipeline/` | `phase-1-intake-and-chronology.md` | Active |
| Phase 2 — Legal Research (RAG) | `pipeline/` | `phase-2-legal-research.md` | Draft |

*To add an active plan, create it in `docs/plan/<category>/<feature>.md` and update this table.*

---

## Overview

The project is a **Case Prep Assistant** automating the three grunt-work phases common to every legal case:

1. **Intake (#5)** — Aggregate scattered case documents into a structured, organized matter.
2. **Chronology Builder (#4)** — Extract dates, events, and people from documents into a sorted, interactive timeline.
3. **Legal Research (#2)** — Retrieve relevant precedents via RAG over a case law corpus.

Phases 1 and 2 form the core deliverable. Phase 3 is a planned extension.

## Implementation Order

```
Phase 1 ──────────────▶ Phase 2 ──────────────▶ (future)
Intake + Chronology      Legal Research
(scaffold → ingest →     (corpus → embed →
 OCR → extract →          RAG → brief gen)
 dedupe → timeline →
 export)
```

## Key Principles

1. **Each phase is independently runnable and testable.**
2. **Tasks are ordered for incremental checkpoints** — mark `[x]` as you go.
3. **If interrupted, resume from the last `[x]` task.**
4. **Phase 1 output (timeline data) feeds Phase 2 as context.**
