"""Corpus ingestion API routes."""

import logging
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.corpus_document import CorpusDocument
from app.schemas.corpus import CorpusDocumentResponse, IngestionReport
from app.services.corpus import CorpusService, document_to_response, parse_corpus_file
from app.services.embedding import get_embedding_service
from app.services.vector_store import get_vector_store
from app.storage import storage_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/corpus", tags=["corpus"])

ALLOWED_EXTENSIONS = {".json", ".jsonl"}


def _build_service(db: AsyncSession) -> CorpusService:
    """Build a CorpusService wired to the configured embedder / vector store.

    Kept as a module function so tests can monkeypatch the factories.
    """
    return CorpusService(
        db=db,
        embedder=get_embedding_service(),
        vector_store=get_vector_store(),
        storage=storage_provider,
    )


@router.post(
    "/ingest",
    response_model=IngestionReport,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_corpus_endpoint(
    file: UploadFile = File(..., description="Corpus file (.json or .jsonl)"),
    case_name: str | None = Form(None, description="Optional override for case name"),
    citation: str | None = Form(None, description="Optional override for citation"),
    court: str | None = Form(None, description="Optional override for court"),
    jurisdiction: str | None = Form(None, description="Optional override for jurisdiction"),
    year: int | None = Form(None, description="Optional override for year"),
    db: AsyncSession = Depends(get_db),
) -> IngestionReport:
    """Ingest an uploaded corpus file.

    Flow: validate format → duplicate check → save original to R2 →
    parse/chunk/embed/store → return an :class:`IngestionReport`.
    """
    filename = file.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file format '{ext}'; allowed: .json, .jsonl",
        )

    content = await file.read()
    overrides = {
        k: v
        for k, v in {
            "case_name": case_name,
            "citation": citation,
            "court": court,
            "jurisdiction": jurisdiction,
            "year": year,
        }.items()
        if v is not None
    }

    # ── Parse + validate before touching storage ───────────────────────────
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="corpus_", suffix=ext, delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        records = parse_corpus_file(tmp_path)
        if not records:
            raise HTTPException(status_code=400, detail="Corpus file contains no records")
        metadata, _text = CorpusService._parse_document(records[0])
        candidate = {**metadata, **overrides}
        if not candidate.get("case_name") or not candidate.get("citation"):
            raise HTTPException(
                status_code=400, detail="case_name and citation are required"
            )
    except HTTPException:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001 — convert parse errors to 400
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to parse corpus file: {exc}"
        ) from exc

    # ── Duplicate check (same case_name + citation) ────────────────────────
    dup = await db.execute(
        select(CorpusDocument).where(
            CorpusDocument.case_name == candidate["case_name"],
            CorpusDocument.citation == candidate["citation"],
        )
    )
    if dup.scalar_one_or_none():
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Document '{candidate['case_name']}' "
                f"({candidate['citation']}) already exists"
            ),
        )

    # ── Save original file to R2 / storage ─────────────────────────────────
    object_key = await storage_provider.save(f"corpus/{uuid.uuid4()}", filename, content)

    # ── Ingest ─────────────────────────────────────────────────────────────
    service = _build_service(db)
    start = time.monotonic()
    try:
        assert tmp_path is not None
        await service.ingest_file(tmp_path, storage_path=object_key, overrides=overrides)
        return IngestionReport(
            documents_ingested=service.documents_ingested,
            chunks_created=service.chunks_created,
            elapsed_seconds=round(time.monotonic() - start, 3),
        )
    except Exception as exc:  # noqa: BLE001 — ingestion failures → 500
        logger.exception("Corpus ingestion failed for %s", filename)
        # Mark any documents created for this upload as failed.
        result = await db.execute(
            select(CorpusDocument).where(CorpusDocument.storage_path == object_key)
        )
        for doc in result.scalars().all():
            doc.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=500, detail=f"Ingestion failed: {exc}"
        ) from exc
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@router.get("/documents", response_model=list[CorpusDocumentResponse])
async def list_corpus_documents(db: AsyncSession = Depends(get_db)):
    """List all ingested corpus documents (newest first)."""
    return await _build_service(db).list_documents()


@router.get("/documents/{corpus_document_id}", response_model=CorpusDocumentResponse)
async def get_corpus_document(
    corpus_document_id: str, db: AsyncSession = Depends(get_db)
):
    """Get a single corpus document (used for ingestion status polling)."""
    doc = await _build_service(db).get_document(corpus_document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Corpus document not found")
    return document_to_response(doc)


@router.delete(
    "/documents/{corpus_document_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_corpus_document(
    corpus_document_id: str, db: AsyncSession = Depends(get_db)
):
    """Delete a corpus document: R2 file → vector chunks → DB record."""
    try:
        deleted = await _build_service(db).delete_document(corpus_document_id)
    except Exception as exc:  # noqa: BLE001 — deletion failures → 500
        logger.exception("Failed to delete corpus document %s", corpus_document_id)
        raise HTTPException(
            status_code=500, detail=f"Delete failed: {exc}"
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Corpus document not found")
