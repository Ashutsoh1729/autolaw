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
    storage_provider: str = "local"
    upload_dir: str = str(Path(__file__).resolve().parent.parent / "uploads")
    max_file_size_mb: int = 50
    max_matter_total_mb: int = 500

    # S3-compatible storage (used when storage_provider = "s3")
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = ""

    # OCR
    tesseract_cmd: str = "/opt/homebrew/bin/tesseract"

    # LLM via OpenRouter (optional — used in Steps 5-6)
    # Set AUTOLAW_OPENROUTER_API_KEY to enable LLM extraction.
    # Change AUTOLAW_LLM_MODEL to any OpenRouter model slug, e.g.:
    #   "openai/gpt-4o-mini", "anthropic/claude-3-5-haiku",
    #   "deepseek/deepseek-chat", "google/gemini-2.0-flash-001"
    openrouter_api_key: str = ""
    llm_model: str = "openai/gpt-4o-mini"
    llm_base_url: str = "https://openrouter.ai/api/v1"

    # Email ingestion (placeholder for Phase 2)
    email_domain: str = "matter.autolaw.app"

    model_config = {"env_prefix": "AUTOLAW_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
