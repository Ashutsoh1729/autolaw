"""Storage provider factory — returns the configured storage backend."""

from app.config import settings
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider


def get_storage_provider() -> StorageProvider:
    """Return a storage provider based on application settings.

    Reads ``settings.storage_provider`` to decide which backend to use:
    - ``"local"`` (default) → :class:`LocalStorageProvider`
    - ``"s3"``             → :class:`S3StorageProvider`
    """
    if settings.storage_provider == "s3":
        # Deferred import so S3 dependencies are optional at runtime.
        from app.storage.s3 import S3StorageProvider

        return S3StorageProvider(
            bucket_name=settings.s3_bucket_name,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url or None,
        )
    return LocalStorageProvider()


# Module-level singleton — importers write ``from app.storage import storage_provider``
storage_provider = get_storage_provider()
