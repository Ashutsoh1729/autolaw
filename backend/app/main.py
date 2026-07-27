"""AutoLaw FastAPI Application — Phase 1: Intake + Chronology Builder."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import matters, documents, timeline, export

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup."""
    logger.info("Starting AutoLaw API...")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info("Shutting down AutoLaw API...")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Legal AI Document Processing Pipeline — Phase 1: Intake + Chronology Builder",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(matters.router)
app.include_router(documents.router)
app.include_router(timeline.router)
app.include_router(export.router)


@app.get("/api/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
