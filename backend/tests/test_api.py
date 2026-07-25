"""Integration tests for the AutoLaw API."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db, engine, Base


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


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """GET /api/health should return ok."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_matter(client: AsyncClient):
    """POST /api/matters should create a new matter."""
    resp = await client.post(
        "/api/matters",
        json={"title": "Test v. Case", "case_type": "Civil"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test v. Case"
    assert data["case_type"] == "Civil"
    assert data["status"] == "active"
    assert data["email_address"] is not None
    assert "id" in data


@pytest.mark.asyncio
async def test_create_matter_validation(client: AsyncClient):
    """POST /api/matters with empty title should fail."""
    resp = await client.post("/api/matters", json={"title": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_matters(client: AsyncClient):
    """GET /api/matters should return all matters."""
    # Create two matters
    await client.post("/api/matters", json={"title": "Case 1"})
    await client.post("/api/matters", json={"title": "Case 2"})

    resp = await client.get("/api/matters")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["matters"]) == 2


@pytest.mark.asyncio
async def test_get_matter(client: AsyncClient):
    """GET /api/matters/{id} should return a single matter."""
    create_resp = await client.post(
        "/api/matters", json={"title": "My Case"}
    )
    matter_id = create_resp.json()["id"]

    resp = await client.get(f"/api/matters/{matter_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "My Case"


@pytest.mark.asyncio
async def test_get_matter_not_found(client: AsyncClient):
    """GET /api/matters/{id} for non-existent ID should return 404."""
    resp = await client.get("/api/matters/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_matter(client: AsyncClient):
    """PATCH /api/matters/{id} should update the matter."""
    create_resp = await client.post(
        "/api/matters", json={"title": "Old Title"}
    )
    matter_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/matters/{matter_id}",
        json={"title": "New Title", "status": "archived"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Title"
    assert data["status"] == "archived"


@pytest.mark.asyncio
async def test_delete_matter(client: AsyncClient):
    """DELETE /api/matters/{id} should remove the matter."""
    create_resp = await client.post(
        "/api/matters", json={"title": "Delete Me"}
    )
    matter_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/matters/{matter_id}")
    assert resp.status_code == 204

    # Verify it's gone
    resp = await client.get(f"/api/matters/{matter_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_document(client: AsyncClient):
    """POST /api/matters/{id}/documents should upload a file."""
    # Create matter first
    matter_resp = await client.post(
        "/api/matters", json={"title": "Doc Test"}
    )
    matter_id = matter_resp.json()["id"]

    # Upload a text file
    files = {"files": ("test.txt", b"Hello, this is a test document for OCR.", "text/plain")}
    resp = await client.post(
        f"/api/matters/{matter_id}/documents",
        files=files,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 1
    assert data[0]["filename"] == "test.txt"
    assert data[0]["original_type"] == "txt"
    assert data[0]["processing_status"] == "pending"


@pytest.mark.asyncio
async def test_upload_invalid_file_type(client: AsyncClient):
    """Uploading a .exe file should be rejected."""
    matter_resp = await client.post(
        "/api/matters", json={"title": "Invalid File Test"}
    )
    matter_id = matter_resp.json()["id"]

    files = {"files": ("virus.exe", b"fake exe content", "application/octet-stream")}
    resp = await client.post(
        f"/api/matters/{matter_id}/documents",
        files=files,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient):
    """GET /api/matters/{id}/documents should list uploaded files."""
    matter_resp = await client.post(
        "/api/matters", json={"title": "List Docs Test"}
    )
    matter_id = matter_resp.json()["id"]

    # Upload two files
    for fname in ["a.txt", "b.txt"]:
        files = {"files": (fname, b"content", "text/plain")}
        await client.post(f"/api/matters/{matter_id}/documents", files=files)

    resp = await client.get(f"/api/matters/{matter_id}/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["documents"]) == 2


@pytest.mark.asyncio
async def test_duplicate_filename(client: AsyncClient):
    """Uploading the same filename twice should be rejected."""
    matter_resp = await client.post(
        "/api/matters", json={"title": "Dedup Test"}
    )
    matter_id = matter_resp.json()["id"]

    files = {"files": ("dup.txt", b"content", "text/plain")}
    resp1 = await client.post(f"/api/matters/{matter_id}/documents", files=files)
    assert resp1.status_code == 201

    files2 = {"files": ("dup.txt", b"different content", "text/plain")}
    resp2 = await client.post(f"/api/matters/{matter_id}/documents", files=files2)
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_process_document(client: AsyncClient):
    """POST /api/matters/{id}/documents/{docId}/process should extract text."""
    import tempfile
    import os

    # Create a PDF file with some text
    matter_resp = await client.post(
        "/api/matters", json={"title": "Process Test"}
    )
    matter_id = matter_resp.json()["id"]

    # Upload a simple text file (fast path, no actual OCR needed)
    files = {"files": ("hello.txt", b"This is a test document for processing.", "text/plain")}
    upload_resp = await client.post(
        f"/api/matters/{matter_id}/documents",
        files=files,
    )
    doc_id = upload_resp.json()[0]["id"]

    # Process the document
    resp = await client.post(
        f"/api/matters/{matter_id}/documents/{doc_id}/process"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_timeline_endpoint(client: AsyncClient):
    """GET /api/matters/{id}/timeline should return events."""
    matter_resp = await client.post(
        "/api/matters", json={"title": "Timeline Test"}
    )
    matter_id = matter_resp.json()["id"]

    resp = await client.get(f"/api/matters/{matter_id}/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 0
    assert data["events"] == []


@pytest.mark.asyncio
async def test_export_no_events(client: AsyncClient):
    """Export without events should return 404."""
    matter_resp = await client.post(
        "/api/matters", json={"title": "Export Test"}
    )
    matter_id = matter_resp.json()["id"]

    resp = await client.get(f"/api/matters/{matter_id}/export?format=docx")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_matters(client: AsyncClient):
    """GET /api/matters?search=... should filter by title."""
    await client.post("/api/matters", json={"title": "Smith v. Corp"})
    await client.post("/api/matters", json={"title": "Jones v. State"})

    resp = await client.get("/api/matters?search=Smith")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["matters"][0]["title"] == "Smith v. Corp"

    resp = await client.get("/api/matters?search=Jones")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["matters"][0]["title"] == "Jones v. State"
