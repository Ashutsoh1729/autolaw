"""Document upload, list, and processing API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentListResponse, DocumentProcessResponse, DocumentResponse
from app.services.document import upload_document, list_documents, get_document, document_to_response
from app.services.ocr import extract_text, count_pages
from app.services.chunker import chunk_document
from app.services.classifier import classify_document
from app.services.extractor import extract_events_from_chunk
from app.services.dedup import process_events
from app.storage.local import storage_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/matters/{matter_id}/documents", tags=["Documents"])


@router.post("", response_model=list[DocumentResponse], status_code=status.HTTP_201_CREATED)
async def upload_documents_endpoint(
    matter_id: str,
    files: list[UploadFile] = File(..., description="One or more files to upload"),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or more documents to a matter."""
    responses: list[DocumentResponse] = []

    for file in files:
        content = await file.read()
        try:
            doc = await upload_document(db, matter_id, file.filename or "unnamed", content)
            responses.append(document_to_response(doc))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return responses


@router.get("", response_model=DocumentListResponse)
async def list_documents_endpoint(
    matter_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all documents in a matter."""
    docs, total = await list_documents(db, matter_id, skip=skip, limit=limit)
    responses = [document_to_response(d) for d in docs]
    return DocumentListResponse(documents=responses, total=total)


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document_endpoint(
    matter_id: str, doc_id: str, db: AsyncSession = Depends(get_db)
):
    """Get a single document by ID."""
    doc = await get_document(db, doc_id)
    if not doc or doc.matter_id != matter_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_to_response(doc)


@router.post("/{doc_id}/process", response_model=DocumentProcessResponse)
async def process_document_endpoint(
    matter_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Process a document: OCR → Chunk → Classify → Extract events.

    This is a synchronous endpoint for Phase 1. A production system would use
    background task queues (Celery / Arq) for long-running processing.
    """
    doc = await get_document(db, doc_id)
    if not doc or doc.matter_id != matter_id:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.processing_status in ("extracted",):
        return DocumentProcessResponse(
            document_id=doc_id,
            status="already_processed",
            message="Document has already been processed",
        )

    try:
        # Step 1: Read file
        file_bytes = await storage_provider.read(doc.storage_path)

        # Step 2: OCR / Text Extraction
        doc.processing_status = "ocr_pending"
        await db.flush()

        text = await extract_text(doc.filename, file_bytes)
        doc.ocr_text = text
        doc.page_count = await count_pages(doc.filename, file_bytes)
        doc.processing_status = "ocr_done"
        await db.flush()

        logger.info("OCR complete for doc %s: %d chars extracted", doc_id, len(text))

        if not text.strip():
            doc.processing_status = "failed"
            doc.processing_error = "No text could be extracted from the document"
            await db.flush()
            return DocumentProcessResponse(
                document_id=doc_id,
                status="failed",
                message="No text could be extracted from the document",
            )

        # Step 3: Chunking
        doc.processing_status = "classifying"
        await db.flush()

        chunks = chunk_document(text)
        logger.info("Chunking complete: %d chunks", len(chunks))

        # Step 4: Classify
        doc_type = await classify_document(text)
        doc.doc_type = doc_type
        doc.processing_status = "classifying"  # keep for now
        await db.flush()

        logger.info("Classification: %s", doc_type)

        # Step 5: Event Extraction per chunk
        doc.processing_status = "extracting"
        await db.flush()

        from app.models.event import Event
        import json

        all_events: list[dict] = []
        for chunk in chunks:
            raw_events = await extract_events_from_chunk(chunk.text, chunk.index)
            processed = await process_events(raw_events, matter_id, doc_id, chunk.index)
            all_events.extend(processed)

        logger.info("Extraction complete: %d events found", len(all_events))

        # Store events in DB
        from app.services.dedup import sort_events_chronologically

        for evt_data in all_events:
            event = Event(
                matter_id=matter_id,
                source_document_id=doc_id,
                source_chunk_index=evt_data.get("source_chunk_index"),
                date=str(evt_data.get("date", "")),
                date_precision=evt_data.get("date_precision", "exact"),
                date_end=str(evt_data.get("date_end") or ""),
                title=str(evt_data.get("title", "Untitled Event")),
                description=str(evt_data.get("description", "")),
                people=json.dumps(evt_data.get("people", [])),
                doc_reference=str(evt_data.get("doc_reference", "")),
                confidence=float(evt_data.get("confidence", 0.5)),
                dedup_group=evt_data.get("dedup_group"),
            )
            db.add(event)

        doc.extracted_text = text
        doc.processing_status = "extracted"
        await db.flush()

        preview = text[:500] if text else None
        return DocumentProcessResponse(
            document_id=doc_id,
            status="completed",
            message=f"Processing complete: {len(all_events)} events extracted from {len(chunks)} chunks",
            ocr_text_preview=preview,
        )

    except Exception as e:
        logger.exception("Processing failed for doc %s", doc_id)
        doc.processing_status = "failed"
        doc.processing_error = str(e)
        await db.flush()
        return DocumentProcessResponse(
            document_id=doc_id,
            status="failed",
            message=f"Processing failed: {str(e)}",
        )
