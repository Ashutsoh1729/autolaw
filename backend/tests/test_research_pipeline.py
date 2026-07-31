"""Tests for the Phase 2 Group B research pipeline (search + brief generation).

Covers schema validation, query formulation, reranking, brief generation, and
the full search/brief API pipeline. The vector store / embedding service used
by the endpoints are injected per-test (Group A's modules may not be merged
yet), so tests are hermetic.
"""

import math
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient, ASGITransport

from app.config import settings
from app.database import Base, engine
from app.main import app
from app.routers import research as research_router
from app.schemas.research import (
    BriefCitation,
    BriefSection,
    ResearchBriefRequest,
    ResearchBriefResponse,
    ResearchSearchRequest,
    ResearchSearchResponse,
    ResearchStatusResponse,
)
from app.services.brief_generator import BriefGenerator
from app.services.query_formulator import QueryFormulator
from app.services.reranker import Reranker, SearchResult

# NOTE: async tests are handled by `asyncio_mode = "auto"` in pyproject.toml;
# explicit @pytest.mark.asyncio decorators are used for clarity.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop them after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def reset_pipeline(monkeypatch):
    """Reset research service singletons and the brief cache between tests.

    Also clears the OpenRouter API key so LLM-dependent paths deterministically
    take their fallback branches (tests that need the LLM path set the key
    explicitly via their own monkeypatch).
    """
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    research_router.reset_services()
    research_router.brief_generator.clear_cache()
    saved_reranker = research_router.reranker
    yield
    research_router.reset_services()
    research_router.brief_generator.clear_cache()
    research_router.reranker = saved_reranker


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def create_matter(client: AsyncClient, title: str, jurisdiction: str | None = None) -> str:
    payload = {"title": title}
    if jurisdiction:
        payload["jurisdiction"] = jurisdiction
    resp = await client.post("/api/matters", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


def make_result(
    chunk_id: str,
    text: str = "A passage of legal text discussing duty of care.",
    citation: str = "",
    court: str = "",
    year: int = 0,
    jurisdiction: str = "",
    score: float = 0.5,
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        corpus_document_id=f"doc-{chunk_id}",
        text=text,
        metadata={
            "case_name": f"Case {chunk_id}",
            "citation": citation,
            "court": court,
            "year": year,
            "jurisdiction": jurisdiction,
        },
        score=score,
    )


def make_brief(
    brief_id: str = "brief-1",
    matter_id: str = "m1",
    query: str = "q",
    status: str = "complete",
) -> ResearchBriefResponse:
    return ResearchBriefResponse(
        id=brief_id,
        matter_id=matter_id,
        query=query,
        created_at=datetime.now(timezone.utc),
        summary="Synthetic summary for tests.",
        sections=[
            BriefSection(
                title="Key Precedents",
                content="The law requires a duty of care.",
                citations=[
                    BriefCitation(
                        citation="248 N.Y. 339",
                        passage="A store owner must keep premises reasonably safe.",
                        relevance_score=0.9,
                        corpus_document_id="doc-p1",
                    )
                ],
            )
        ],
        status=status,
    )


# ---------------------------------------------------------------------------
# Step 1: Schema validation
# ---------------------------------------------------------------------------

class TestResearchSchemas:
    def test_search_request_defaults(self):
        req = ResearchSearchRequest(query="negligence")
        assert req.query_type == "auto"
        assert req.filters is None
        assert req.top_k == 10

    def test_search_request_invalid_query(self):
        with pytest.raises(Exception):
            ResearchSearchRequest(query="")

    def test_search_request_invalid_top_k(self):
        with pytest.raises(Exception):
            ResearchSearchRequest(query="x", top_k=0)
        with pytest.raises(Exception):
            ResearchSearchRequest(query="x", top_k=51)

    def test_search_request_invalid_query_type(self):
        with pytest.raises(Exception):
            ResearchSearchRequest(query="x", query_type="bogus")

    def test_search_response_roundtrip(self):
        item = {
            "chunk_id": "c1",
            "corpus_document_id": "d1",
            "text": "some text",
            "case_name": "Marbury v. Madison",
            "citation": "5 U.S. 137",
            "court": "SCOTUS",
            "year": 1803,
            "relevance_score": 0.87,
        }
        resp = ResearchSearchResponse(
            results=[item], total_results=1, query_used="judicial review"
        )
        data = resp.model_dump()
        assert data["results"][0]["citation"] == "5 U.S. 137"
        assert data["total_results"] == 1
        assert data["status"] == "ok"

    def test_brief_request_optional_query(self):
        req = ResearchBriefRequest()
        assert req.query is None
        assert req.regenerate is False
        req2 = ResearchBriefRequest(query="duty of care", regenerate=True)
        assert req2.query == "duty of care"

    def test_brief_response_status_validation(self):
        with pytest.raises(Exception):
            ResearchBriefResponse(
                id="b", matter_id="m", query="q", created_at=datetime.now(timezone.utc),
                summary="s", status="bogus",
            )

    def test_status_response_default(self):
        st = ResearchStatusResponse()
        assert st.status == "not_generated"
        assert st.brief_id is None
        assert st.brief is None


# ---------------------------------------------------------------------------
# Step 2: Query formulation
# ---------------------------------------------------------------------------

class TestQueryFormulator:
    @pytest.mark.asyncio
    async def test_formulate_known_context(self):
        qf = QueryFormulator()
        ctx = {
            "title": "Smith v. Jones",
            "description": "Plaintiff alleges negligence and breach of contract by the defendant.",
            "jurisdiction": "New York",
        }
        queries = await qf.formulate(ctx, [])
        assert queries[0] == "Smith negligence liability New York"
        assert any("breach of contract" in q for q in queries)
        assert 1 <= len(queries) <= 3

    @pytest.mark.asyncio
    async def test_formulate_extracts_people_from_events(self):
        qf = QueryFormulator()
        ctx = {"jurisdiction": "California"}
        events = [
            {
                "title": "Lease signed",
                "description": "Commercial lease agreement executed.",
                "people": ["Acme Corp"],
            },
            {
                "title": "Breach",
                "description": "Acme failed to pay rent, breach of lease claim.",
                "people": [],
            },
        ]
        queries = await qf.formulate(ctx, events)
        assert any("Acme Corp" in q for q in queries)
        assert any("breach of lease" in q for q in queries)

    @pytest.mark.asyncio
    async def test_formulate_empty_timeline_single_general_query(self):
        qf = QueryFormulator()
        ctx = {
            "description": "Client involved in an incident with a business partner",
            "jurisdiction": "California",
        }
        queries = await qf.formulate(ctx, [])
        assert len(queries) == 1
        assert queries[0] == "involved incident business partner California"

    @pytest.mark.asyncio
    async def test_formulate_empty_context_returns_fallback(self):
        qf = QueryFormulator()
        queries = await qf.formulate({}, [])
        assert len(queries) == 1
        assert queries[0] == "liability"

    @pytest.mark.asyncio
    async def test_formulate_llm_mode_when_key_set(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
        qf = QueryFormulator()
        called = {}

        async def fake_llm(matter_context, timeline_events):
            called["yes"] = True
            return ["custom legal query from llm"]

        monkeypatch.setattr(qf, "_formulate_with_llm", fake_llm)
        queries = await qf.formulate({"description": "some matter"}, [])
        assert queries == ["custom legal query from llm"]
        assert called.get("yes")

    @pytest.mark.asyncio
    async def test_extract_key_issues(self):
        qf = QueryFormulator()
        issues = await qf.extract_key_issues(
            {"description": "claims of negligence and fraud against the company"}
        )
        assert "negligence claim" in issues
        assert "fraud claim" in issues

    @pytest.mark.asyncio
    async def test_extract_key_issues_fallback(self):
        qf = QueryFormulator()
        issues = await qf.extract_key_issues({"description": "nothing here"})
        assert issues == ["general liability"]


# ---------------------------------------------------------------------------
# Step 3: Reranker
# ---------------------------------------------------------------------------

class TestReranker:
    @pytest.mark.asyncio
    async def test_rerank_orders_by_score_descending(self):
        reranker = Reranker(scorer=lambda q, r: {"a": 0.3, "b": 0.9, "c": 0.7}[r.chunk_id])
        results = [make_result("a"), make_result("b"), make_result("c")]
        out = await reranker.rerank("query", results, top_k=5)
        assert [r.chunk_id for r in out] == ["b", "c", "a"]
        scores = [r.score for r in out]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_rerank_top_k_truncation(self):
        reranker = Reranker(scorer=lambda q, r: float(len(r.chunk_id)))
        results = [make_result(f"c{i}") for i in range(5)]
        out = await reranker.rerank("query", results, top_k=2)
        assert len(out) == 2

    @pytest.mark.asyncio
    async def test_rerank_empty_input(self):
        assert await Reranker().rerank("query", []) == []

    @pytest.mark.asyncio
    async def test_rerank_lexical_fallback_normalizes_scores(self):
        # sentence-transformers absent -> deterministic lexical fallback
        reranker = Reranker(mode="cross-encoder")
        results = [
            make_result("c1", text="negligence in driving caused the injury"),
            make_result("c2", text="unrelated contract boilerplate"),
        ]
        out = await reranker.rerank("negligence liability", results, top_k=5)
        assert out[0].chunk_id == "c1"
        for r in out:
            assert 0.0 <= r.score <= 1.0

    @pytest.mark.asyncio
    async def test_rerank_mock_cross_encoder(self, monkeypatch):
        from app.services import reranker as reranker_module

        monkeypatch.setattr(reranker_module, "_HAS_SENTENCE_TRANSFORMERS", True)
        reranker = Reranker(mode="cross-encoder")
        results = [make_result("c1"), make_result("c2")]

        async def fake_cross_encoder(query, results):
            return [reranker._scored_copy(r, s) for r, s in zip(results, [0.4, 0.9])]

        monkeypatch.setattr(reranker, "_rerank_cross_encoder", fake_cross_encoder)
        out = await reranker.rerank("query", results, top_k=5)
        assert [r.chunk_id for r in out] == ["c2", "c1"]
        assert out[0].score == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_rerank_mock_llm(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
        reranker = Reranker(mode="llm")
        results = [make_result("c1"), make_result("c2")]

        async def fake_llm(query, results):
            return [reranker._scored_copy(r, s) for r, s in zip(results, [0.2, 0.8])]

        monkeypatch.setattr(reranker, "_rerank_llm", fake_llm)
        out = await reranker.rerank("query", results, top_k=5)
        assert [r.chunk_id for r in out] == ["c2", "c1"]


# ---------------------------------------------------------------------------
# Step 4: Brief generator
# ---------------------------------------------------------------------------

class TestBriefGenerator:
    @pytest.mark.asyncio
    async def test_generate_with_mock_llm(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
        gen = BriefGenerator()
        passages = [
            make_result("p1", citation="248 N.Y. 339", text="premises liability passage", score=0.9),
            make_result("p2", citation="1932 AC 562", text="duty of care passage", score=0.7),
        ]

        async def fake_llm(query, passages, matter_context):
            return make_brief(
                brief_id="llm-brief",
                matter_id=matter_context.get("matter_id", "?"),
                query=query,
            )

        monkeypatch.setattr(gen, "_synthesize_with_llm", fake_llm)
        brief = await gen.generate("premises liability", passages, {"matter_id": "m1"})
        assert brief.status == "complete"
        assert brief.matter_id == "m1"
        assert brief.query == "premises liability"
        # valid citation passes verification
        assert len(brief.sections[0].citations) == 1
        assert brief.sections[0].citations[0].citation == "248 N.Y. 339"

    @pytest.mark.asyncio
    async def test_citation_verification_removes_hallucinated(self):
        gen = BriefGenerator()
        passages = [make_result("p1", citation="248 N.Y. 339", text="real passage", score=0.9)]
        brief = ResearchBriefResponse(
            id="b1",
            matter_id="m1",
            query="q",
            created_at=datetime.now(timezone.utc),
            summary="s",
            sections=[
                BriefSection(
                    title="T",
                    content="C",
                    citations=[
                        BriefCitation(
                            citation="248 N.Y. 339", passage="real", relevance_score=0.9,
                            corpus_document_id="doc-p1",
                        ),
                        BriefCitation(
                            citation="999 F.3d 999", passage="hallucinated", relevance_score=0.9,
                            corpus_document_id="doc-zzz",
                        ),
                    ],
                )
            ],
            status="complete",
        )
        verified = gen._verify_citations(brief, passages)
        assert [c.citation for c in verified.sections[0].citations] == ["248 N.Y. 339"]

    @pytest.mark.asyncio
    async def test_citation_verification_fills_missing_doc_id(self):
        gen = BriefGenerator()
        passages = [make_result("p1", citation="5 U.S. 137", text="Marbury passage", score=0.9)]
        brief = ResearchBriefResponse(
            id="b1", matter_id="m1", query="q", created_at=datetime.now(timezone.utc),
            summary="s",
            sections=[
                BriefSection(
                    title="T", content="C",
                    citations=[
                        BriefCitation(
                            citation="5 U.S. 137", passage="", relevance_score=0.9,
                            corpus_document_id="",
                        )
                    ],
                )
            ],
            status="complete",
        )
        verified = gen._verify_citations(brief, passages)
        cit = verified.sections[0].citations[0]
        assert cit.corpus_document_id == "doc-p1"

    @pytest.mark.asyncio
    async def test_llm_unavailable_no_results(self):
        # No API key configured -> LLM unavailable; no passages -> no_results
        gen = BriefGenerator()
        brief = await gen.generate("negligence", [], {"matter_id": "m1"})
        assert brief.status == "no_results"
        assert brief.summary
        assert brief.sections == []

    @pytest.mark.asyncio
    async def test_llm_unavailable_extractive_partial(self):
        gen = BriefGenerator()
        passages = [
            make_result("p1", citation="248 N.Y. 339", text="premises liability passage", score=0.9),
            make_result("p2", citation="1932 AC 562", text="duty of care passage", score=0.6),
        ]
        brief = await gen.generate("negligence", passages, {"matter_id": "m1"})
        assert brief.status == "partial"
        assert brief.sections[0].title == "Relevant Passages"
        assert len(brief.sections[0].citations) == 2
        assert brief.summary.startswith("premises liability passage")

    @pytest.mark.asyncio
    async def test_caching_returns_cached_brief(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
        gen = BriefGenerator()
        passages = [make_result("p1", citation="248 N.Y. 339", text="premises liability", score=0.9)]
        calls = {"n": 0}

        async def fake_llm(query, passages, matter_context):
            calls["n"] += 1
            return make_brief(brief_id=f"llm-{calls['n']}", matter_id="m1", query=query)

        monkeypatch.setattr(gen, "_synthesize_with_llm", fake_llm)
        b1 = await gen.generate("premises liability", passages, {"matter_id": "m1"})
        b2 = await gen.generate("premises liability", passages, {"matter_id": "m1"})
        assert b1.id == b2.id
        assert calls["n"] == 1  # no second LLM call

    @pytest.mark.asyncio
    async def test_force_regeneration_bypasses_cache(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
        gen = BriefGenerator()
        passages = [make_result("p1", citation="248 N.Y. 339", text="premises liability", score=0.9)]
        calls = {"n": 0}

        async def fake_llm(query, passages, matter_context):
            calls["n"] += 1
            return make_brief(brief_id=f"llm-{calls['n']}", matter_id="m1", query=query)

        monkeypatch.setattr(gen, "_synthesize_with_llm", fake_llm)
        b1 = await gen.generate("premises liability", passages, {"matter_id": "m1"})
        b2 = await gen.generate("premises liability", passages, {"matter_id": "m1"}, force=True)
        assert calls["n"] == 2
        assert b1.id != b2.id

    @pytest.mark.asyncio
    async def test_regenerate_updates_cache(self, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
        gen = BriefGenerator()
        passages = [make_result("p1", citation="248 N.Y. 339", text="premises liability", score=0.9)]
        calls = {"n": 0}

        async def fake_llm(query, passages, matter_context):
            calls["n"] += 1
            return make_brief(brief_id=f"llm-{calls['n']}", matter_id="m1", query=query)

        monkeypatch.setattr(gen, "_synthesize_with_llm", fake_llm)
        b1 = await gen.generate("old query", passages, {"matter_id": "m1"})
        b2 = await gen.regenerate(b1.id, "new query", passages, {"matter_id": "m1"})
        assert b2.query == "new query"
        assert gen.get_brief("m1").id == b2.id

    @pytest.mark.asyncio
    async def test_passage_truncation_fits_token_budget(self):
        gen = BriefGenerator()
        long_passages = [
            SearchResult(
                chunk_id=f"c{i}",
                corpus_document_id="dx",
                text="word " * 3000,
                metadata={"citation": "1 U.S. 1"},
                score=1.0 - i * 0.01,
            )
            for i in range(100)
        ]
        truncated = gen._truncate_passages(long_passages)
        assert 0 < len(truncated) < len(long_passages)
        budget_chars = (128_000 - 4_000) * 4
        used = sum(len(p.text) + 200 for p in truncated)
        assert used <= budget_chars

    def test_generate_summary_uses_top_passage(self):
        gen = BriefGenerator()
        summary = gen._generate_summary(
            [
                make_result("low", text="low scored passage text", score=0.2),
                make_result("top", text="highest scored passage text here", score=0.95),
            ]
        )
        assert summary.startswith("highest scored passage text here")


# ---------------------------------------------------------------------------
# Step 7: Integration tests — search + brief pipeline
# ---------------------------------------------------------------------------

class TestResearchSearchEndpoint:
    async def test_search_returns_expected_results(self, client):
        mid = await create_matter(client, "Slip and Fall", "New York")
        store = research_router.InMemoryVectorStore()
        store.seed(
            [
                make_result(
                    "ch1", citation="248 N.Y. 339", court="NY Court of Appeals", year=1928,
                    jurisdiction="New York",
                    text="A store owner must keep premises reasonably safe for invitees.",
                ),
                make_result(
                    "ch2", citation="1932 AC 562", court="House of Lords", year=1932,
                    jurisdiction="UK",
                    text="The neighbour principle establishes a duty of care.",
                ),
            ]
        )
        research_router.vector_store = store

        resp = await client.post(
            f"/api/matters/{mid}/research/search",
            json={"query": "premises liability", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 2
        assert data["query_used"] == "premises liability"
        assert data["status"] == "ok"
        ids = {item["chunk_id"] for item in data["results"]}
        assert ids == {"ch1", "ch2"}
        for item in data["results"]:
            assert item["case_name"]
            assert item["citation"]
            assert 0.0 <= item["relevance_score"] <= 1.0

    async def test_search_with_filters_narrows_results(self, client):
        mid = await create_matter(client, "Filter Test", "New York")
        store = research_router.InMemoryVectorStore()
        store.seed(
            [
                make_result(
                    "f1", citation="248 N.Y. 339", court="NY Court of Appeals", year=1928,
                    jurisdiction="New York", text="premises liability ruling in New York",
                ),
                make_result(
                    "f2", citation="5 U.S. 137", court="SCOTUS", year=1803,
                    jurisdiction="federal", text="judicial review in federal court",
                ),
                make_result(
                    "f3", citation="410 U.S. 113", court="SCOTUS", year=1973,
                    jurisdiction="federal", text="privacy rights decision",
                ),
            ]
        )
        research_router.vector_store = store

        resp = await client.post(
            f"/api/matters/{mid}/research/search",
            json={
                "query": "court decision",
                "top_k": 10,
                "filters": {"court": "SCOTUS", "year_from": 1900, "year_to": 1980},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = {item["chunk_id"] for item in data["results"]}
        assert ids == {"f3"}
        for item in data["results"]:
            assert item["court"] == "SCOTUS"
            assert 1900 <= item["year"] <= 1980

    async def test_search_empty_corpus_returns_no_results(self, client):
        mid = await create_matter(client, "Empty Corpus", "Texas")
        # No store injected -> empty fallback store
        resp = await client.post(
            f"/api/matters/{mid}/research/search",
            json={"query": "negligence"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 0
        assert data["results"] == []
        assert data["status"] == "no_results"

    async def test_search_vector_store_down_degrades_gracefully(self, client):
        mid = await create_matter(client, "Store Down", "Texas")

        class BrokenStore:
            async def search(self, *args, **kwargs):
                raise ConnectionError("qdrant is unreachable")

        research_router.vector_store = BrokenStore()
        resp = await client.post(
            f"/api/matters/{mid}/research/search",
            json={"query": "negligence"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_results"
        assert data["message"]
        assert data["results"] == []

    async def test_search_embedding_unavailable_returns_503(self, client):
        mid = await create_matter(client, "Embedding Down", "Texas")

        class BrokenEmbedder:
            def embed(self, text):
                raise ConnectionError("openrouter unavailable")

        research_router.embedding_service = BrokenEmbedder()
        resp = await client.post(
            f"/api/matters/{mid}/research/search",
            json={"query": "negligence"},
        )
        assert resp.status_code == 503

    async def test_search_matter_not_found(self, client):
        resp = await client.post(
            "/api/matters/does-not-exist/research/search",
            json={"query": "negligence"},
        )
        assert resp.status_code == 404


class TestResearchBriefEndpoint:
    async def _seed_store(self, passages):
        store = research_router.InMemoryVectorStore()
        store.seed(passages)
        research_router.vector_store = store

    async def test_brief_generation_with_mock_llm(self, client, monkeypatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
        mid = await create_matter(client, "Brief Matter", "New York")
        await self._seed_store(
            [
                make_result(
                    "p1", citation="248 N.Y. 339", court="NY Court of Appeals", year=1928,
                    jurisdiction="New York", text="A store owner must keep premises reasonably safe.",
                    score=0.9,
                ),
                make_result(
                    "p2", citation="1932 AC 562", court="House of Lords", year=1932,
                    jurisdiction="UK", text="The neighbour principle establishes a duty of care.",
                    score=0.7,
                ),
            ]
        )

        async def fake_llm(query, passages, matter_context):
            return make_brief(
                brief_id="llm-brief-1",
                matter_id=matter_context.get("matter_id", "?"),
                query=query,
            )

        monkeypatch.setattr(research_router.brief_generator, "_synthesize_with_llm", fake_llm)

        resp = await client.post(f"/api/matters/{mid}/research/brief", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert data["matter_id"] == mid
        assert data["sections"][0]["title"] == "Key Precedents"
        assert data["sections"][0]["citations"][0]["citation"] == "248 N.Y. 339"

    async def test_brief_caching_second_call_returns_same_brief(self, client):
        mid = await create_matter(client, "Cache Me", "California")
        await self._seed_store(
            [make_result("c1", citation="5 U.S. 137", text="Marbury establishes judicial review.", score=0.9)]
        )

        r1 = await client.post(f"/api/matters/{mid}/research/brief", json={})
        r2 = await client.post(f"/api/matters/{mid}/research/brief", json={})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]
        assert r1.json()["status"] == "partial"

    async def test_brief_regenerate_returns_different_brief(self, client):
        mid = await create_matter(client, "Regen Me", "New York")
        await self._seed_store(
            [make_result("r1", citation="248 N.Y. 339", text="premises liability passage", score=0.9)]
        )

        r1 = await client.post(f"/api/matters/{mid}/research/brief", json={})
        r2 = await client.post(
            f"/api/matters/{mid}/research/brief/regenerate",
            json={"query": "duty of care"},
        )
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["id"] != r2.json()["id"]
        assert r2.json()["query"] == "duty of care"

    async def test_brief_empty_corpus_returns_no_results(self, client):
        mid = await create_matter(client, "No Corpus", "Texas")
        resp = await client.post(f"/api/matters/{mid}/research/brief", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_results"
        assert "No relevant" in data["summary"]
        assert data["sections"] == []

    async def test_brief_regenerate_empty_corpus(self, client):
        mid = await create_matter(client, "No Corpus Regen", "Texas")
        resp = await client.post(
            f"/api/matters/{mid}/research/brief/regenerate",
            json={"query": "anything"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_results"

    async def test_brief_embedding_unavailable_returns_503(self, client):
        mid = await create_matter(client, "Embed Down Brief", "Texas")

        class BrokenEmbedder:
            def embed(self, text):
                raise ConnectionError("openrouter unavailable")

        research_router.embedding_service = BrokenEmbedder()
        resp = await client.post(f"/api/matters/{mid}/research/brief", json={})
        assert resp.status_code == 503

    async def test_brief_matter_not_found(self, client):
        resp = await client.post("/api/matters/does-not-exist/research/brief", json={})
        assert resp.status_code == 404


class TestResearchStatusEndpoint:
    async def test_status_not_generated_before_brief(self, client):
        mid = await create_matter(client, "Status Test", "Texas")
        resp = await client.get(f"/api/matters/{mid}/research/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_generated"
        assert data["brief_id"] is None
        assert data["brief"] is None

    async def test_status_after_brief_generation(self, client):
        mid = await create_matter(client, "Status Test 2", "New York")
        store = research_router.InMemoryVectorStore()
        store.seed([make_result("s1", citation="248 N.Y. 339", text="premises liability passage", score=0.9)])
        research_router.vector_store = store

        brief_resp = await client.post(f"/api/matters/{mid}/research/brief", json={})
        brief_id = brief_resp.json()["id"]

        resp = await client.get(f"/api/matters/{mid}/research/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["brief_id"] == brief_id
        assert data["status"] == "partial"
        assert data["brief"]["id"] == brief_id
        assert data["brief"]["matter_id"] == mid

    async def test_get_brief_endpoint_returns_current_brief(self, client):
        mid = await create_matter(client, "Get Brief", "California")
        store = research_router.InMemoryVectorStore()
        store.seed([make_result("g1", citation="5 U.S. 137", text="Marbury establishes judicial review.", score=0.9)])
        research_router.vector_store = store

        # Before generation
        resp = await client.get(f"/api/matters/{mid}/research/brief")
        assert resp.json()["status"] == "not_generated"

        brief_resp = await client.post(f"/api/matters/{mid}/research/brief", json={})
        brief_id = brief_resp.json()["id"]

        resp = await client.get(f"/api/matters/{mid}/research/brief")
        data = resp.json()
        assert data["brief_id"] == brief_id
        assert data["brief"]["status"] == "partial"

    async def test_status_matter_not_found(self, client):
        resp = await client.get("/api/matters/does-not-exist/research/status")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Fallback store (used until Group A's vector store is merged)
# ---------------------------------------------------------------------------

class TestInMemoryVectorStore:
    @pytest.mark.asyncio
    async def test_search_roundtrip_and_cosine_scoring(self):
        store = research_router.InMemoryVectorStore()
        store.seed(
            [
                make_result("a", text="negligence duty of care claim"),
                make_result("b", text="breach of contract damages"),
            ]
        )
        embedder = research_router.DeterministicEmbeddingService()
        results = await store.search(embedder.embed("negligence duty"), top_k=5)
        assert {r.chunk_id for r in results} == {"a", "b"}
        assert results[0].score >= results[1].score

    @pytest.mark.asyncio
    async def test_search_filters(self):
        store = research_router.InMemoryVectorStore()
        store.seed(
            [
                make_result("a", court="SCOTUS", year=1803, jurisdiction="federal", text="marbury"),
                make_result("b", court="SCOTUS", year=1973, jurisdiction="federal", text="roe"),
                make_result("c", court="NY Court of Appeals", year=1928, jurisdiction="New York", text="palsgraf"),
            ]
        )
        embedder = research_router.DeterministicEmbeddingService()
        results = await store.search(
            embedder.embed("case"),
            top_k=10,
            filters={"court": "SCOTUS", "year_from": 1900, "year_to": 1980},
        )
        assert [r.chunk_id for r in results] == ["b"]

        results = await store.search(
            embedder.embed("case"), top_k=10, filters={"jurisdiction": "New York"}
        )
        assert [r.chunk_id for r in results] == ["c"]

    @pytest.mark.asyncio
    async def test_search_empty_collection(self):
        store = research_router.InMemoryVectorStore()
        results = await store.search([1.0, 0.0], top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_collection_info(self):
        store = research_router.InMemoryVectorStore()
        info = await store.collection_info()
        assert info["total_points"] == 0
        assert info["dimension"] == 8
