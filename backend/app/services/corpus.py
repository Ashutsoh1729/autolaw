"""Corpus ingestion service — parse, chunk, embed, store.

Orchestrates the ingestion pipeline:

    Raw corpus files (JSON / JSONL)
      → parse into structured records (case metadata + full text)
      → chunk text with overlap (token-count aware)
      → embed chunks via :class:`EmbeddingService`
      → store chunks via :class:`VectorStore`
      → ingestion report

The module also exposes a CLI::

    python -m app.services.corpus ingest --dir corpus_data/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.corpus_document import CorpusDocument
from app.schemas.corpus import (
    CorpusChunkSchema,
    CorpusDocumentResponse,
    IngestionReport,
)
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore, get_vector_store
from app.storage import storage_provider

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".json", ".jsonl"}

# Default chunking parameters (max_chunk_size measured in ~tokens).
DEFAULT_MAX_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
CHARS_PER_TOKEN = 4

# Default seed-corpus location (repo root / backend / corpus_data).
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent.parent.parent / "corpus_data"


def estimate_tokens(text: str) -> int:
    """Rough token estimate for English text (~4 chars per token)."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def parse_corpus_file(filepath: str | Path) -> list[dict[str, Any]]:
    """Parse a corpus file into a list of raw records.

    - ``.json`` — a single object (or a list of objects) → list of records
    - ``.jsonl`` — one JSON object per line → list of records
    """
    path = Path(filepath)
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON on line {lineno} of {path}: {exc}"
                    ) from exc
        return records
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return [data]
    raise ValueError(
        f"Unsupported corpus file format '{suffix}'; expected .json or .jsonl"
    )


class CorpusService:
    """Parses, chunks, embeds, and stores corpus documents."""

    def __init__(
        self,
        db: AsyncSession,
        embedder: EmbeddingService | None = None,
        vector_store: VectorStore | None = None,
        storage: Any | None = None,
    ) -> None:
        self.db = db
        self.embedder = embedder or EmbeddingService()
        self.vector_store = vector_store or get_vector_store()
        self.storage = storage or storage_provider
        # Counters for the current ingestion run (read by the API for reports).
        self.documents_ingested = 0
        self.chunks_created = 0

    # ── Public API ─────────────────────────────────────────────────────────

    async def ingest_file(
        self,
        filepath: str | Path,
        storage_path: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> CorpusDocumentResponse:
        """Parse a single corpus file and ingest its records.

        - ``.json`` single object → one document; ``.jsonl`` → one document
          per line (all records are ingested).
        - ``overrides`` (case_name, citation, court, jurisdiction, year) are
          merged into each record's metadata; when provided, only the first
          record is ingested (the upload represents one logical document).

        Returns the response of the first ingested document. The total counts
        for the run are available via ``documents_ingested`` /
        ``chunks_created``.
        """
        self._reset_counters()
        records = parse_corpus_file(filepath)
        if not records:
            raise ValueError("Corpus file contains no records")
        if overrides:
            records = [records[0]]
        responses = await self._ingest_records(
            records, storage_path=storage_path, overrides=overrides
        )
        return responses[0]

    async def ingest_directory(self, path: str | Path) -> IngestionReport:
        """Walk a directory and ingest every ``.json`` / ``.jsonl`` file.

        Per-file failures are logged and skipped so one bad file doesn't
        abort the whole run.
        """
        self._reset_counters()
        start = time.monotonic()
        root = Path(path)
        files = sorted(
            p
            for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        for filepath in files:
            try:
                records = parse_corpus_file(filepath)
                await self._ingest_records(records, storage_path=None)
            except Exception:
                logger.exception("Skipping failed corpus file: %s", filepath)
        elapsed = time.monotonic() - start
        return IngestionReport(
            documents_ingested=self.documents_ingested,
            chunks_created=self.chunks_created,
            elapsed_seconds=round(elapsed, 3),
        )

    async def list_documents(self) -> list[CorpusDocumentResponse]:
        """List all ingested corpus documents (newest first)."""
        result = await self.db.execute(
            select(CorpusDocument).order_by(CorpusDocument.created_at.desc())
        )
        return [document_to_response(doc) for doc in result.scalars().all()]

    async def get_document(self, corpus_document_id: str) -> CorpusDocument | None:
        """Fetch a single corpus document by ID."""
        return await self.db.get(CorpusDocument, corpus_document_id)

    async def delete_document(self, corpus_document_id: str) -> bool:
        """Delete a corpus document and all associated artifacts.

        Deletion order (plan-mandated):
          1. delete the original file from R2 / storage via ``storage_path``
          2. delete chunks from the vector store
          3. delete the ``CorpusDocument`` record from the database

        If any step fails, the DB transaction is rolled back and the error
        is re-raised.
        """
        doc = await self.db.get(CorpusDocument, corpus_document_id)
        if not doc:
            return False
        try:
            if doc.storage_path:
                await self.storage.delete(doc.storage_path)
            await self.vector_store.delete_chunks(corpus_document_id)
            await self.db.delete(doc)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return True

    # ── Internal pipeline ──────────────────────────────────────────────────

    def _reset_counters(self) -> None:
        self.documents_ingested = 0
        self.chunks_created = 0

    async def _ingest_records(
        self,
        records: list[dict[str, Any]],
        storage_path: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> list[CorpusDocumentResponse]:
        responses: list[CorpusDocumentResponse] = []
        for record in records:
            metadata, text = self._parse_document(record)
            if overrides:
                metadata.update(
                    {k: v for k, v in overrides.items() if v is not None}
                )
            doc, chunk_count = await self._ingest_record(
                metadata,
                text,
                storage_path=storage_path,
                embedding_model=self.embedder.model,
                embedding_dimension=self.embedder.embed_dimension(),
            )
            self.documents_ingested += 1
            self.chunks_created += chunk_count
            responses.append(document_to_response(doc))
        await self.db.commit()
        return responses

    async def _ingest_record(
        self,
        metadata: dict[str, Any],
        text: str,
        storage_path: str | None,
        embedding_model: str,
        embedding_dimension: int,
    ) -> tuple[CorpusDocument, int]:
        """Create the DB record, chunk/embed/store text, mark ready."""
        doc = CorpusDocument(
            case_name=str(metadata["case_name"]),
            citation=str(metadata["citation"]),
            court=str(metadata["court"]),
            jurisdiction=str(metadata["jurisdiction"]),
            year=int(metadata["year"]),
            url=metadata.get("url"),
            summary=metadata.get("summary"),
            storage_path=storage_path,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            status="ingesting",
        )
        self.db.add(doc)
        await self.db.flush()

        chunk_texts = self._chunk_text(
            text, max_chunk_size=DEFAULT_MAX_CHUNK_SIZE, overlap=DEFAULT_CHUNK_OVERLAP
        )
        chunks = [
            CorpusChunkSchema(
                corpus_document_id=doc.id,
                chunk_index=index,
                text=chunk_text,
                metadata=dict(metadata),
            )
            for index, chunk_text in enumerate(chunk_texts)
        ]
        if chunks:
            embeddings = self.embedder.embed_batch([c.text for c in chunks])
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding
            await self.vector_store.store_chunks(chunks)

        doc.status = "ready"
        await self.db.flush()
        return doc, len(chunks)

    @staticmethod
    def _parse_document(record: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Extract (metadata, full_text) from a raw corpus record."""
        required = ("case_name", "citation", "court", "jurisdiction", "year", "text")
        missing = [key for key in required if not record.get(key)]
        if missing:
            raise ValueError(
                f"Corpus record missing required fields: {', '.join(missing)}"
            )
        metadata = {
            "case_name": str(record["case_name"]),
            "citation": str(record["citation"]),
            "court": str(record["court"]),
            "jurisdiction": str(record["jurisdiction"]),
            "year": int(record["year"]),
        }
        if record.get("url"):
            metadata["url"] = str(record["url"])
        if record.get("summary"):
            metadata["summary"] = str(record["summary"])
        return metadata, str(record["text"])

    @staticmethod
    def _chunk_text(
        text: str, max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP
    ) -> list[str]:
        """Split text into chunks of ~``max_chunk_size`` tokens.

        Token count is estimated at ~4 chars per token. Chunks prefer
        paragraph / sentence boundaries and carry ``overlap`` tokens of
        context between consecutive chunks.
        """
        if not text or not text.strip():
            return []
        max_chars = max(1, max_chunk_size * CHARS_PER_TOKEN)
        overlap_chars = max(0, overlap * CHARS_PER_TOKEN)
        text_len = len(text)
        chunks: list[str] = []
        start = 0
        while start < text_len:
            end = min(start + max_chars, text_len)
            if end < text_len:
                para_break = text.rfind("\n\n", start, end)
                if para_break > start + max_chars // 2:
                    end = para_break + 2
                else:
                    sentence_end = max(
                        text.rfind(". ", start, end),
                        text.rfind("! ", start, end),
                        text.rfind("? ", start, end),
                        text.rfind("\n", start, end),
                    )
                    if sentence_end > start + max_chars // 2:
                        end = sentence_end + 2
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)
            if end >= text_len:
                break
            start = max(end - overlap_chars, start + 1)
        return chunks


def document_to_response(doc: CorpusDocument) -> CorpusDocumentResponse:
    """Convert a CorpusDocument ORM model to its Pydantic response."""
    return CorpusDocumentResponse(
        id=doc.id,
        case_name=doc.case_name,
        citation=doc.citation,
        court=doc.court,
        jurisdiction=doc.jurisdiction,
        year=doc.year,
        url=doc.url,
        summary=doc.summary,
        storage_path=doc.storage_path,
        embedding_model=doc.embedding_model,
        embedding_dimension=doc.embedding_dimension,
        status=doc.status,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def _run_cli(args: argparse.Namespace) -> None:
    """Shared CLI runner (also used when invoked via ``python -m``)."""
    from app.database import async_session_factory, init_db

    await init_db()
    async with async_session_factory() as session:
        service = CorpusService(
            db=session,
            embedder=EmbeddingService(),
            vector_store=get_vector_store(),
            storage=storage_provider,
        )
        report = await service.ingest_directory(args.dir)
    print(json.dumps(report.model_dump(), indent=2))


def main() -> None:
    """Entry point for ``python -m app.services.corpus``."""
    parser = argparse.ArgumentParser(
        prog="python -m app.services.corpus",
        description="AutoLaw corpus ingestion CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a corpus directory")
    ingest_parser.add_argument(
        "--dir",
        default=str(DEFAULT_CORPUS_DIR),
        help=f"Directory with .json/.jsonl corpus files (default: {DEFAULT_CORPUS_DIR})",
    )
    args = parser.parse_args()
    asyncio.run(_run_cli(args))


if __name__ == "__main__":
    main()
