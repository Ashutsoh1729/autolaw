"""Application configuration via environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "AutoLaw API"
    debug: bool = False

    # Database
    database_url: str = "sqlite+aiosqlite:///./uploads/autolaw.db"

    # File storage
    upload_dir: str = str(Path(__file__).resolve().parent.parent / "uploads")
    max_file_size_mb: int = 50
    max_matter_total_mb: int = 500

    # OCR
    tesseract_cmd: str = "/opt/homebrew/bin/tesseract"

    # LLM (optional — used in Steps 5-6)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    # Email ingestion (placeholder for Phase 2)
    email_domain: str = "matter.autolaw.app"

    model_config = {"env_prefix": "AUTOLAW_", "env_file": ".env"}


settings = Settings()
