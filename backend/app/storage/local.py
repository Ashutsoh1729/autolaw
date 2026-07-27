"""Local filesystem storage provider for uploaded documents."""

import os
import shutil
from pathlib import Path

import aiofiles

from app.config import settings
from app.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    """Store and retrieve files on the local filesystem."""

    def __init__(self, base_path: str | None = None) -> None:
        self.base_path = Path(base_path or settings.upload_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _matter_dir(self, matter_id: str) -> Path:
        """Return the directory for a given matter, creating it if needed."""
        path = self.base_path / "matters" / matter_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save(self, matter_id: str, filename: str, content: bytes) -> str:
        """Save a file and return its relative storage path."""
        matter_dir = self._matter_dir(matter_id)
        # Avoid filename collisions by prefixing with hash
        safe_name = f"{hash(content)}_{filename}"
        file_path = matter_dir / safe_name
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
        return str(file_path.relative_to(self.base_path))

    async def read(self, storage_path: str) -> bytes:
        """Read a file's contents by its storage path."""
        full_path = self.base_path / storage_path
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    def get_full_path(self, storage_path: str) -> str:
        """Return the absolute filesystem path for a stored file."""
        return str(self.base_path / storage_path)

    async def delete(self, storage_path: str) -> None:
        """Delete a stored file."""
        full_path = self.base_path / storage_path
        if full_path.exists():
            full_path.unlink()

    async def delete_matter_dir(self, matter_id: str) -> None:
        """Delete the entire directory for a matter."""
        matter_dir = self.base_path / "matters" / matter_id
        if matter_dir.exists():
            shutil.rmtree(matter_dir)

    async def get_matter_usage_bytes(self, matter_id: str) -> int:
        """Calculate total bytes of stored files for a matter."""
        matter_dir = self.base_path / "matters" / matter_id
        if not matter_dir.exists():
            return 0
        total = 0
        for f in matter_dir.iterdir():
            if f.is_file():
                total += f.stat().st_size
        return total


# Singleton
storage_provider = LocalStorageProvider()
