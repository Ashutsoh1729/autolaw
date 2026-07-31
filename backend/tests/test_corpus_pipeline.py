"""Tests for the Phase 2 Group A corpus ingestion pipeline.

Covers: schema validation (Step 1), the CorpusDocument model (Step 2),
chunking / token estimation (Step 4), the EmbeddingService with a mocked
OpenRouter client (Step 5), the VectorStore interface with an in-memory
Qdrant (Step 6), seed-corpus ingestion (Step 7), the end-to-end pipeline
(Step 8), and the /api/corpus endpoints (Step 9).

All tests are hermetic: embeddings use a deterministic fake embedder and
the vector store uses ``AsyncQdrantClient(location=":memory:")``.
"""

import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.database import Base, async_session_factory, engine
from app.main import app
from app.models.corpus_document import CorpusDocument
from app.schemas.corpus import (
    CorpusChunkSchema,
    CorpusDocumentCreate,
    IngestionReport,
)
from app.services.corpus import CorpusService, estimate_tokens, parse_corpus_file
from app.services.embedding import EmbeddingService
from app.services.vector_store import QdrantVectorStore, SearchResult
from app.storage import storage_provider

CORPUS_DATA_DIR = Path(__file__).resolve().parent.parent / "corpus_data"

# A valid single-record corpus file payload used across tests.
RECORD = {
    "case_name": "Marbury v. Madison",
    "citation": "5 U.S. 137",
    "court": "Supreme Court of the United States",
    "jurisdiction": "federal",
    "year": 1803,
    "text": (
        "Chief Justice Marshall held that it is emphatically the province and "
        "duty of the judicial department to say what the law is. A law "
        "repugnant to the Constitution is void. The decision established the "
        "power of judicial review in the United States."
    ),
}


# ── Fakes ───────────────────────────────────────────────────────────────────

def _hash_vector(text: str, dimension: int) -> list[float]:
    """Deterministic pseudo-vector for a text (same text → same vector)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [
        round(((digest[i] % 256) / 255.0) * 2 - 1, 6) for i in range(dimension)
    ]


class FakeEmbedder:
    """Stands in for EmbeddingService in service/API tests."""

    def __init__(self, dimension: int = 8, model: str = "fake-embed-test") -> None:
        self.dimension = dimension
        self.model = model
        self.calls: list[list[str]] = []

    def embed_dimension(self) -> int:
        return self.dimension

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [_hash_vector(t, self.dimension) for t in texts]


class FakeEmbedding:
    def __init__(self, index: int, embedding: list[float]) -> None:
        self.index = index
        self.embedding = embedding


class FakeEmbeddingsAPI:
    """Fake OpenAI-compatible ``client.embeddings.create``."""

    def __init__(self, dimension: int = 8, fail_models: set[str] | None = None) -> None:
        self.dimension = dimension
        self.fail_models = fail_models or set()
        self.calls: list[tuple[str, list[str]]] = []

    def create(self, model: str, input, **kwargs) -> SimpleNamespace:
        texts = input if isinstance(input, list) else [input]
        self.calls.append((model, texts))
        if model in self.fail_models:
            raise RuntimeError(f"model {model} unavailable")
        data = [
            FakeEmbedding(index=i, embedding=_hash_vector(t, self.dimension))
            for i, t in enumerate(texts)
        ]
        return SimpleNamespace(data=data)


class FakeOpenAIClient:
    def __init__(self, **kwargs) -> None:
        self.embeddings = FakeEmbeddingsAPI(**kwargs)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop them after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db():
    async with async_session_factory() as session:
        yield session


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder(dimension=8)


@pytest.fixture
async def memory_store() -> QdrantVectorStore:
    from qdrant_client import AsyncQdrantClient

    store = QdrantVectorStore(
        client=AsyncQdrantClient(location=":memory:"), dimension=8
    )
    yield store
    await store._client.close()


@pytest.fixture
async def client(monkeypatch, memory_store, fake_embedder):
    """API client with the router's embedder / vector store factories patched."""
    import app.routers.corpus as corpus_router

    monkeypatch.setattr(corpus_router, "get_vector_store", lambda: memory_store)
    monkeypatch.setattr(corpus_router, "get_embedding_service", lambda: fake_embedder)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Step 1: Schema validation ───────────────────────────────────────────────

def test_schema_valid_document():
    doc = CorpusDocumentCreate(
        case_name="Marbury v. Madison",
        citation="5 U.S. 137",
        court="Supreme Court of the United States",
        jurisdiction="federal",
        year=1803,
        url="https://example.com/marbury",
        summary="Judicial review case.",
    )
    assert doc.case_name == "Marbury v. Madison"
    assert doc.year == 1803
    assert doc.url is not None
    assert doc.summary is not None


def test_schema_missing_required_fields():
    with pytest.raises(ValidationError):
        CorpusDocumentCreate(
            case_name="Marbury v. Madison",
            citation="5 U.S. 137",
            court="Supreme Court of the United States",
            # missing jurisdiction
            year=1803,
        )
    with pytest.raises(ValidationError):
        CorpusDocumentCreate(
            case_name="",  # empty case name
            citation="5 U.S. 137",
            court="Supreme Court of the United States",
            jurisdiction="federal",
            year=1803,
        )


def test_schema_wrong_types():
    with pytest.raises(ValidationError):
        CorpusDocumentCreate(
            case_name="Marbury v. Madison",
            citation="5 U.S. 137",
            court="Supreme Court of the United States",
            jurisdiction="federal",
            year="eighteen-oh-three",  # not an int
        )
    with pytest.raises(ValidationError):
        CorpusDocumentCreate(
            case_name=123,  # not a str
            citation="5 U.S. 137",
            court="Supreme Court of the United States",
            jurisdiction="federal",
            year=1803,
        )


def test_schema_chunk_defaults():
    chunk = CorpusChunkSchema(
        corpus_document_id="doc-1", chunk_index=0, text="hello"
    )
    assert chunk.id is None
    assert chunk.metadata == {}
    assert chunk.embedding is None
    chunk_with_values = CorpusChunkSchema(
        id="chunk-1",
        corpus_document_id="doc-1",
        chunk_index=1,
        text="hello",
        metadata={"court": "SCOTUS"},
        embedding=[1.0, 2.0],
    )
    assert chunk_with_values.id == "chunk-1"
    assert chunk_with_values.metadata == {"court": "SCOTUS"}
    assert chunk_with_values.embedding == [1.0, 2.0]


def test_schema_ingestion_report():
    report = IngestionReport(
        documents_ingested=2, chunks_created=10, elapsed_seconds=1.25
    )
    assert report.documents_ingested == 2
    assert report.chunks_created == 10
    assert report.elapsed_seconds == 1.25


# ── Step 2: CorpusDocument model CRUD ───────────────────────────────────────

async def test_corpus_document_model_crud(db):
    doc = CorpusDocument(
        case_name="Marbury v. Madison",
        citation="5 U.S. 137",
        court="Supreme Court of the United States",
        jurisdiction="federal",
        year=1803,
        storage_path="corpus/abc/marbury.jsonl",
        status="pending",
    )
    db.add(doc)
    await db.commit()

    fetched = await db.get(CorpusDocument, doc.id)
    assert fetched is not None
    assert fetched.case_name == "Marbury v. Madison"
    assert fetched.status == "pending"
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.embedding_model is None

    # Update
    fetched.status = "ready"
    fetched.embedding_model = "nvidia/nemotron-3-embed-1b:free"
    fetched.embedding_dimension = 1024
    await db.commit()

    again = await db.get(CorpusDocument, doc.id)
    assert again.status == "ready"
    assert again.embedding_model == "nvidia/nemotron-3-embed-1b:free"
    assert again.embedding_dimension == 1024

    # Delete
    await db.delete(again)
    await db.commit()
    assert await db.get(CorpusDocument, doc.id) is None


# ── Step 4: chunking / token estimation / parsing ───────────────────────────

def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("hello world") == 2  # 11 chars // 4
    assert estimate_tokens("word " * 100) == 125  # 500 chars // 4


def test_chunk_text_empty():
    assert CorpusService._chunk_text("") == []
    assert CorpusService._chunk_text("   \n\t ") == []


def test_chunk_text_single_short():
    chunks = CorpusService._chunk_text(
        "A short opinion.", max_chunk_size=512, overlap=64
    )
    assert chunks == ["A short opinion."]


def test_chunk_text_respects_budget():
    text = "word " * 2000  # ~10000 chars, ~2500 tokens
    chunks = CorpusService._chunk_text(text, max_chunk_size=100, overlap=10)
    assert len(chunks) > 1
    max_chars = 100 * 4
    assert all(len(c) <= max_chars + 10 for c in chunks)
    # Overlap: consecutive chunks should share some trailing context.
    assert chunks[0][-max_chars // 2 :] in chunks[1]


def test_chunk_text_paragraph_boundaries():
    text = "\n\n".join(["Paragraph " + str(i) + " content " * 30 for i in range(4)])
    chunks = CorpusService._chunk_text(text, max_chunk_size=200, overlap=20)
    assert len(chunks) > 1
    # Every chunk is non-empty and trimmed.
    assert all(c and c == c.strip() for c in chunks)


def test_parse_corpus_file_jsonl(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps({"case_name": "A", "citation": "1", "text": "x"})
        + "\n"
        + json.dumps({"case_name": "B", "citation": "2", "text": "y"})
        + "\n\n",
        encoding="utf-8",
    )
    records = parse_corpus_file(path)
    assert len(records) == 2
    assert records[0]["case_name"] == "A"
    assert records[1]["case_name"] == "B"


def test_parse_corpus_file_json(tmp_path):
    path = tmp_path / "case.json"
    path.write_text(json.dumps({"case_name": "A", "citation": "1", "text": "x"}), encoding="utf-8")
    records = parse_corpus_file(path)
    assert len(records) == 1
    assert records[0]["case_name"] == "A"
    # A JSON array is also supported.
    path.write_text(
        json.dumps([{"case_name": "A"}, {"case_name": "B"}]), encoding="utf-8"
    )
    assert len(parse_corpus_file(path)) == 2


def test_parse_corpus_file_invalid_format(tmp_path):
    path = tmp_path / "case.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_corpus_file(path)


def test_parse_document_missing_fields():
    with pytest.raises(ValueError, match="missing required fields"):
        CorpusService._parse_document(
            {"case_name": "A", "citation": "1", "text": "x"}
        )


async def test_ingest_file_jsonl(db, fake_embedder, memory_store, tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_name": "Case A",
                "citation": "1 A. 1",
                "court": "Test Court",
                "jurisdiction": "federal",
                "year": 2001,
                "text": "Alpha opinion text " * 20,
            }
        )
        + "\n"
        + json.dumps(
            {
                "case_name": "Case B",
                "citation": "2 B. 2",
                "court": "Test Court",
                "jurisdiction": "federal",
                "year": 2002,
                "text": "Beta opinion text " * 20,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    service = CorpusService(
        db=db, embedder=fake_embedder, vector_store=memory_store, storage=storage_provider
    )
    resp = await service.ingest_file(path, storage_path="corpus/test/upload.jsonl")

    assert resp.case_name == "Case A"
    assert resp.status == "ready"
    assert resp.storage_path == "corpus/test/upload.jsonl"
    assert service.documents_ingested == 2
    assert service.chunks_created == 2

    docs = await service.list_documents()
    assert len(docs) == 2
    assert {d.case_name for d in docs} == {"Case A", "Case B"}
    assert all(d.embedding_model == "fake-embed-test" for d in docs)
    assert all(d.embedding_dimension == 8 for d in docs)

    info = await memory_store.collection_info()
    assert info["total_points"] == 2
    assert info["dimension"] == 8


async def test_ingest_file_overrides_single_document(db, fake_embedder, memory_store, tmp_path):
    path = tmp_path / "multi.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_name": "Original v. Name",
                "citation": "9 U. 9",
                "court": "Some Court",
                "jurisdiction": "federal",
                "year": 1990,
                "text": "Opinion body " * 10,
            }
        )
        + "\n"
        + json.dumps(
            {
                "case_name": "Second v. Doc",
                "citation": "8 U. 8",
                "court": "Some Court",
                "jurisdiction": "federal",
                "year": 1991,
                "text": "Second opinion body " * 10,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    service = CorpusService(
        db=db, embedder=fake_embedder, vector_store=memory_store, storage=storage_provider
    )
    resp = await service.ingest_file(
        path,
        overrides={"case_name": "Renamed v. Case", "year": 1999},
    )
    # With overrides, only the first record is ingested.
    assert service.documents_ingested == 1
    assert resp.case_name == "Renamed v. Case"
    assert resp.year == 1999
    docs = await service.list_documents()
    assert len(docs) == 1


# ── Step 5: EmbeddingService ────────────────────────────────────────────────

def _svc(**kwargs) -> EmbeddingService:
    kwargs.setdefault("dimension", 8)
    kwargs.setdefault("max_retries", 1)
    kwargs.setdefault("base_delay", 0)
    return EmbeddingService(**kwargs)


def test_embed_dimension():
    svc = _svc(client=FakeOpenAIClient())
    assert svc.embed_dimension() == 8


def test_embed_returns_expected_dimension():
    fake = FakeOpenAIClient()
    svc = _svc(client=fake)
    vector = svc.embed("hello world")
    assert isinstance(vector, list)
    assert len(vector) == 8


def test_embed_batch_returns_count():
    fake = FakeOpenAIClient()
    svc = _svc(client=fake)
    vectors = svc.embed_batch(["one", "two", "three"])
    assert len(vectors) == 3
    assert all(len(v) == 8 for v in vectors)


def test_embed_batch_empty():
    svc = _svc(client=FakeOpenAIClient())
    assert svc.embed_batch([]) == []


def test_embed_caching():
    fake = FakeOpenAIClient()
    svc = _svc(client=fake)
    v1 = svc.embed("cache me")
    v2 = svc.embed("cache me")
    assert v1 == v2
    # Only one API call should have been made.
    assert len(fake.embeddings.calls) == 1


def test_embed_fallback_on_primary_failure():
    fake = FakeOpenAIClient(fail_models={"primary-model"})
    svc = _svc(
        client=fake,
        model="primary-model",
        fallback_model="fallback-model",
        max_retries=0,
    )
    vector = svc.embed("recover me")
    assert len(vector) == 8
    models_called = [model for model, _ in fake.embeddings.calls]
    assert models_called == ["primary-model", "fallback-model"]


def test_embed_truncates_long_input():
    fake = FakeOpenAIClient()
    svc = _svc(client=fake, max_input_tokens=512)
    long_text = "word " * 2000  # ~10000 chars, far over the token budget
    svc.embed(long_text)
    embedded_text = fake.embeddings.calls[0][1][0]
    assert len(embedded_text) <= 512 * 4


def test_embed_all_models_fail():
    fake = FakeOpenAIClient(fail_models={"primary", "fallback"})
    svc = _svc(client=fake, model="primary", fallback_model="fallback")
    with pytest.raises(Exception, match="All embedding models failed"):
        svc.embed("boom")


# ── Step 6: VectorStore interface + Qdrant implementation ───────────────────

async def test_vector_store_store_and_search_round_trip(memory_store):
    chunks = [
        CorpusChunkSchema(
            id="11111111-1111-1111-1111-111111111111",
            corpus_document_id="doc-1",
            chunk_index=0,
            text="Marbury established judicial review.",
            metadata={"case_name": "Marbury v. Madison", "court": "SCOTUS", "year": 1803},
            embedding=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ),
        CorpusChunkSchema(
            id="22222222-2222-2222-2222-222222222222",
            corpus_document_id="doc-1",
            chunk_index=1,
            text="Gideon requires appointed counsel.",
            metadata={"case_name": "Gideon v. Wainwright", "court": "SCOTUS", "year": 1963},
            embedding=[0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ),
    ]
    ids = await memory_store.store_chunks(chunks)
    assert ids == [c.id for c in chunks]

    results = await memory_store.search([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0].chunk_id == "11111111-1111-1111-1111-111111111111"
    assert results[0].score >= results[1].score
    assert results[0].corpus_document_id == "doc-1"
    assert results[0].metadata["court"] == "SCOTUS"
    assert results[0].text == "Marbury established judicial review."


async def test_vector_store_filters(memory_store):
    chunks = [
        CorpusChunkSchema(
            id=f"10000000-0000-0000-0000-00000000000{i}",
            corpus_document_id=f"doc-{i}",
            chunk_index=0,
            text=f"case text {i}",
            metadata={"court": "SCOTUS" if i % 2 == 0 else "CA", "year": 1800 + i},
            embedding=[float(i % 2), float(1 - i % 2), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )
        for i in range(4)
    ]
    await memory_store.store_chunks(chunks)

    scotus = await memory_store.search(
        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], top_k=10, filters={"court": "SCOTUS"}
    )
    assert len(scotus) == 2
    assert all(r.metadata["court"] == "SCOTUS" for r in scotus)

    year_filter = await memory_store.search(
        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], top_k=10, filters={"year": 1801}
    )
    assert len(year_filter) == 1
    assert year_filter[0].corpus_document_id == "doc-1"


async def test_vector_store_empty_collection(memory_store):
    results = await memory_store.search(
        [0.5] * 8, top_k=5, filters={"court": "SCOTUS"}
    )
    assert results == []
    info = await memory_store.collection_info()
    assert info["total_points"] == 0
    assert info["dimension"] == 8


async def test_vector_store_delete_chunks(memory_store):
    chunks = [
        CorpusChunkSchema(
            id=f"20000000-0000-0000-0000-00000000000{i}",
            corpus_document_id="doc-to-delete",
            chunk_index=i,
            text=f"chunk {i}",
            metadata={},
            embedding=[1.0 if i == 0 else 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )
        for i in range(3)
    ]
    await memory_store.store_chunks(chunks)
    assert (await memory_store.collection_info())["total_points"] == 3

    deleted = await memory_store.delete_chunks("doc-to-delete")
    assert deleted == 3
    assert (await memory_store.collection_info())["total_points"] == 0
    assert await memory_store.search([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]) == []


async def test_vector_store_store_chunks_requires_embedding(memory_store):
    chunk = CorpusChunkSchema(
        corpus_document_id="doc-1", chunk_index=0, text="no vector here"
    )
    with pytest.raises(ValueError, match="no embedding"):
        await memory_store.store_chunks([chunk])


async def test_vector_store_rejects_dimension_mismatch(memory_store):
    chunk = CorpusChunkSchema(
        corpus_document_id="doc-1",
        chunk_index=0,
        text="wrong dim",
        embedding=[1.0, 2.0, 3.0],
    )
    with pytest.raises(ValueError, match="dimension"):
        await memory_store.store_chunks([chunk])


def test_search_result_dataclass():
    result = SearchResult(
        chunk_id="c1",
        corpus_document_id="d1",
        text="hello",
        metadata={"court": "SCOTUS"},
        score=0.9,
    )
    assert result.chunk_id == "c1"
    assert result.score == 0.9


# ── Step 4b: delete_document ordering ────────────────────────────────────────

async def test_delete_document_order(db, fake_embedder):
    events: list[tuple[str, str]] = []

    class FakeStorage:
        async def delete(self, storage_path: str) -> None:
            events.append(("storage", storage_path))

    class FakeVectorStore:
        async def delete_chunks(self, corpus_document_id: str) -> int:
            events.append(("vector", corpus_document_id))
            return 2

    doc = CorpusDocument(
        case_name="Delete Me v. Court",
        citation="9 D. 9",
        court="Test Court",
        jurisdiction="federal",
        year=2000,
        storage_path="corpus/xyz/file.jsonl",
        status="ready",
    )
    db.add(doc)
    await db.commit()

    service = CorpusService(
        db=db, embedder=fake_embedder, vector_store=FakeVectorStore(), storage=FakeStorage()
    )
    assert await service.delete_document(doc.id) is True

    # Order: R2 file → vector chunks → DB record.
    assert events == [("storage", "corpus/xyz/file.jsonl"), ("vector", doc.id)]
    assert await db.get(CorpusDocument, doc.id) is None


async def test_delete_document_missing_returns_false(db, fake_embedder):
    service = CorpusService(db=db, embedder=fake_embedder, vector_store=object(), storage=object())
    assert await service.delete_document("does-not-exist") is False


async def test_delete_document_rollback_on_storage_failure(db, fake_embedder):
    class BadStorage:
        async def delete(self, storage_path: str) -> None:
            raise RuntimeError("R2 outage")

    doc = CorpusDocument(
        case_name="Keep Me",
        citation="1 K. 1",
        court="Test Court",
        jurisdiction="federal",
        year=2001,
        storage_path="corpus/abc/file.jsonl",
        status="ready",
    )
    db.add(doc)
    await db.commit()

    service = CorpusService(
        db=db, embedder=fake_embedder, vector_store=object(), storage=BadStorage()
    )
    with pytest.raises(RuntimeError, match="R2 outage"):
        await service.delete_document(doc.id)
    # DB record must survive the rollback.
    assert await db.get(CorpusDocument, doc.id) is not None


# ── Step 7: seed corpus ingestion ───────────────────────────────────────────

async def test_ingest_seed_corpus(db, fake_embedder, memory_store):
    assert CORPUS_DATA_DIR.exists(), "seed corpus missing"
    service = CorpusService(
        db=db, embedder=fake_embedder, vector_store=memory_store, storage=storage_provider
    )
    report = await service.ingest_directory(CORPUS_DATA_DIR)

    assert report.documents_ingested >= 10
    assert report.chunks_created >= report.documents_ingested
    assert report.elapsed_seconds >= 0

    docs = await service.list_documents()
    assert len(docs) == report.documents_ingested

    info = await memory_store.collection_info()
    assert info["total_points"] == report.chunks_created

    # The corpus must be searchable.
    results = await memory_store.search(
        fake_embedder.embed("Obergefell v. Hodges same sex marriage"), top_k=3
    )
    assert len(results) == 3
    results = await memory_store.search(
        fake_embedder.embed("Marbury v. Madison"), top_k=3, filters={"year": 1803}
    )
    assert len(results) >= 1


# ── Step 8: end-to-end pipeline ─────────────────────────────────────────────

async def test_corpus_pipeline_end_to_end(db, fake_embedder, memory_store, tmp_path):
    """parse → chunk → embed → store → search → delete."""
    text = (
        "The Commerce Clause grants Congress authority over interstate "
        "navigation and commerce. Chief Justice Marshall broadly defined "
        "commerce as intercourse among the states. The New York monopoly "
        "was struck down. " * 8
    )
    path = tmp_path / "gibbons.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_name": "Gibbons v. Ogden",
                "citation": "22 U.S. 1",
                "court": "Supreme Court of the United States",
                "jurisdiction": "federal",
                "year": 1824,
                "text": text,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    service = CorpusService(
        db=db, embedder=fake_embedder, vector_store=memory_store, storage=storage_provider
    )
    resp = await service.ingest_file(path, storage_path="corpus/e2e/gibbons.jsonl")
    assert resp.status == "ready"
    assert resp.case_name == "Gibbons v. Ogden"
    assert service.chunks_created >= 1

    # Search with the exact embedding of a known chunk → top hit is our doc.
    chunk_texts = CorpusService._chunk_text(text)
    query = fake_embedder.embed(chunk_texts[0])
    results = await memory_store.search(query, top_k=3)
    assert len(results) >= 1
    assert results[0].corpus_document_id == resp.id
    assert results[0].metadata["year"] == 1824

    # Filters narrow results correctly.
    filtered = await memory_store.search(query, top_k=3, filters={"court": "Supreme Court of the United States"})
    assert len(filtered) >= 1
    assert all(r.metadata["court"] == "Supreme Court of the United States" for r in filtered)
    empty = await memory_store.search(query, top_k=3, filters={"court": "Nope"})
    assert empty == []

    # delete_document removes chunks from the vector store.
    assert await service.delete_document(resp.id) is True
    info = await memory_store.collection_info()
    assert info["total_points"] == 0
    assert await db.get(CorpusDocument, resp.id) is None


# ── Step 9: API endpoints ───────────────────────────────────────────────────

async def _post_ingest(client: AsyncClient, **kwargs):
    payload = dict(
        files={
            "file": (
                "marbury.jsonl",
                (json.dumps(RECORD) + "\n").encode("utf-8"),
                "application/json",
            )
        }
    )
    payload.update(kwargs)
    return await client.post("/api/corpus/ingest", **payload)


async def test_api_ingest_valid_upload(client):
    resp = await _post_ingest(client)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["documents_ingested"] == 1
    assert data["chunks_created"] == 1
    assert data["elapsed_seconds"] >= 0

    docs = (await client.get("/api/corpus/documents")).json()
    assert len(docs) == 1
    assert docs[0]["case_name"] == "Marbury v. Madison"
    assert docs[0]["status"] == "ready"


async def test_api_ingest_duplicate_409(client):
    assert (await _post_ingest(client)).status_code == 201
    resp = await _post_ingest(client)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


async def test_api_ingest_invalid_type_400(client):
    resp = await client.post(
        "/api/corpus/ingest",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )
    assert resp.status_code == 400
    assert "Invalid file format" in resp.json()["detail"]


async def test_api_ingest_bad_json_400(client):
    resp = await client.post(
        "/api/corpus/ingest",
        files={"file": ("broken.jsonl", b"{not valid json\n", "application/json")},
    )
    assert resp.status_code == 400


async def test_api_ingest_overrides(client):
    resp = await _post_ingest(
        client,
        data={"case_name": "Renamed v. Case", "year": "1999"},
    )
    assert resp.status_code == 201, resp.text
    docs = (await client.get("/api/corpus/documents")).json()
    assert len(docs) == 1
    assert docs[0]["case_name"] == "Renamed v. Case"
    assert docs[0]["year"] == 1999


async def test_api_ingest_stores_original_file(client):
    content = (json.dumps(RECORD) + "\n").encode("utf-8")
    resp = await client.post(
        "/api/corpus/ingest",
        files={"file": ("marbury.jsonl", content, "application/json")},
    )
    assert resp.status_code == 201, resp.text

    docs = (await client.get("/api/corpus/documents")).json()
    storage_path = docs[0]["storage_path"]
    assert storage_path and "matters/corpus/" in storage_path
    assert await storage_provider.read(storage_path) == content
    # cleanup
    await storage_provider.delete(storage_path)


async def test_api_get_document(client):
    assert (await _post_ingest(client)).status_code == 201
    doc_id = (await client.get("/api/corpus/documents")).json()[0]["id"]

    resp = await client.get(f"/api/corpus/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id
    assert resp.json()["status"] == "ready"

    assert (await client.get("/api/corpus/documents/nope")).status_code == 404


async def test_api_delete_document(client, memory_store):
    assert (await _post_ingest(client)).status_code == 201
    doc = (await client.get("/api/corpus/documents")).json()[0]
    assert (await memory_store.collection_info())["total_points"] == 1

    resp = await client.delete(f"/api/corpus/documents/{doc['id']}")
    assert resp.status_code == 204
    assert (await client.get(f"/api/corpus/documents/{doc['id']}")).status_code == 404
    assert (await memory_store.collection_info())["total_points"] == 0
