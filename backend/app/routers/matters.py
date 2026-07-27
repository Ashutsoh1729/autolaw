"""Matter CRUD API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.matter import MatterCreate, MatterResponse, MatterUpdate, MatterListResponse
from app.services.matter import (
    create_matter,
    get_matter,
    list_matters,
    update_matter,
    delete_matter,
    get_matter_response,
)
from app.storage.local import storage_provider

router = APIRouter(prefix="/api/matters", tags=["Matters"])


@router.post("", response_model=MatterResponse, status_code=status.HTTP_201_CREATED)
async def create_matter_endpoint(data: MatterCreate, db: AsyncSession = Depends(get_db)):
    """Create a new legal matter."""
    matter = await create_matter(db, data)
    return await get_matter_response(db, matter)


@router.get("", response_model=MatterListResponse)
async def list_matters_endpoint(
    search: str | None = Query(None, description="Search by title or case number"),
    status: str | None = Query(None, description="Filter by status (active/archived)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all matters with optional search and filter."""
    matters, total = await list_matters(db, search=search, status=status, skip=skip, limit=limit)
    responses = [await get_matter_response(db, m) for m in matters]
    return MatterListResponse(matters=responses, total=total)


@router.get("/{matter_id}", response_model=MatterResponse)
async def get_matter_endpoint(matter_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single matter by ID."""
    matter = await get_matter(db, matter_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    return await get_matter_response(db, matter)


@router.patch("/{matter_id}", response_model=MatterResponse)
async def update_matter_endpoint(
    matter_id: str, data: MatterUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a matter."""
    matter = await update_matter(db, matter_id, data)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    return await get_matter_response(db, matter)


@router.delete("/{matter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_matter_endpoint(matter_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a matter and its uploaded files."""
    deleted = await delete_matter(db, matter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Matter not found")
    await storage_provider.delete_matter_dir(matter_id)
