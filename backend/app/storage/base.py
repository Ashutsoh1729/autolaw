"""Abstract base class for storage providers."""

from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """Abstract interface for storing and retrieving uploaded documents."""

    @abstractmethod
    async def save(self, matter_id: str, filename: str, content: bytes) -> str:
        """Save a file and return its relative storage path."""
        ...

    @abstractmethod
    async def read(self, storage_path: str) -> bytes:
        """Read a file's contents by its storage path."""
        ...

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """Delete a stored file."""
        ...

    @abstractmethod
    async def delete_matter_dir(self, matter_id: str) -> None:
        """Delete all stored files for a matter."""
        ...

    @abstractmethod
    async def get_matter_usage_bytes(self, matter_id: str) -> int:
        """Calculate total bytes of stored files for a matter."""
        ...
