"""
End-to-end pipeline demo — validates the full document processing flow
using the pattern-based (regex) fallback, so no LLM API key is needed.

Run with:
    uv run python -m pytest tests/test_pipeline_demo.py -v -s

The -s flag shows the timeline output so you can visually verify the results.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import engine, Base


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop them after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def demo_text() -> bytes:
    """Read the police report demo fixture."""
    path = FIXTURES_DIR / "police_report.txt"
    assert path.exists(), f"Fixture not found: {path}"
    return path.read_bytes()


@pytest.mark.asyncio
async def test_pipeline_demo(client: AsyncClient, demo_text: bytes):
    """
    End-to-end demo: create matter → upload .txt file → process →
    verify events → fetch and print timeline.

    Uses only the pattern-based fallback (no LLM key required).
    """
    # ── Step 1: Create a matter ──────────────────────────────────────────
    resp = await client.post(
        "/api/matters",
        json={
            "title": "Police Report Demo — Case #2024-78901",
            "case_type": "Criminal",
            "jurisdiction": "Springfield Municipal Court",
            "description": "Hit and run incident — pipeline demo test",
        },
    )
    assert resp.status_code == 201, f"Create matter failed: {resp.text}"
    matter = resp.json()
    matter_id = matter["id"]
    print(f"\n{'='*70}")
    print(f"✅ Matter created:")
    print(f"   ID:    {matter_id}")
    print(f"   Title: {matter['title']}")
    print(f"{'='*70}")

    # ── Step 2: Upload the demo file ─────────────────────────────────────
    files = {
        "files": (
            "police_report_case_2024-78901.txt",
            demo_text,
            "text/plain",
        )
    }
    resp = await client.post(
        f"/api/matters/{matter_id}/documents",
        files=files,
    )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    doc = resp.json()[0]
    doc_id = doc["id"]
    print(f"✅ Document uploaded:")
    print(f"   ID:       {doc_id}")
    print(f"   Filename: {doc['filename']}")
    print(f"   Type:     {doc['original_type']}")
    print(f"   Status:   {doc['processing_status']}")
    print(f"{'='*70}")

    # ── Step 3: Process the document ─────────────────────────────────────
    resp = await client.post(
        f"/api/matters/{matter_id}/documents/{doc_id}/process"
    )
    assert resp.status_code == 200, f"Process failed: {resp.text}"
    process_result = resp.json()
    print(f"✅ Document processed:")
    print(f"   Status:  {process_result['status']}")
    print(f"   Message: {process_result['message']}")
    print(f"{'='*70}")

    assert process_result["status"] == "completed", (
        f"Processing did not complete: {process_result['message']}"
    )

    # ── Step 4: Fetch the timeline ────────────────────────────────────────
    resp = await client.get(f"/api/matters/{matter_id}/timeline")
    assert resp.status_code == 200, f"Timeline fetch failed: {resp.text}"
    timeline = resp.json()
    total = timeline["total_events"]

    print(f"✅ Timeline: {total} events extracted")
    print(f"{'='*70}")

    # ── Step 5: Verify events were extracted ─────────────────────────────
    assert total > 0, (
        "No events were extracted! The pattern-based fallback should have "
        "found dates in the police report fixture."
    )

    # ── Step 6: Print events for visual inspection ───────────────────────
    print("\n📋 EXTRACTED EVENTS:\n")
    for i, event in enumerate(timeline["events"], 1):
        print(f"  [{i}] {event['date']} — {event['title']}")
        print(f"      Precision: {event['date_precision']}")
        print(f"      Confidence: {event['confidence']}")
        if event.get("description"):
            desc = event["description"]
            print(f"      Description: {desc[:150]}{'...' if len(desc) > 150 else ''}")
        if event.get("people"):
            print(f"      People: {', '.join(event['people'])}")
        if event.get("doc_reference"):
            print(f"      Source: {event['doc_reference']}")
        print()

    print(f"{'='*70}")
    print(f"🎉 Pipeline demo PASSED — {total} events extracted successfully!")
    print(f"{'='*70}\n")
