"""S3-compatible storage provider (AWS S3, Cloudflare R2, MinIO)."""

from __future__ import annotations

from pathlib import Path

import aioboto3

from app.storage.base import StorageProvider


class S3StorageProvider(StorageProvider):
    """Store and retrieve files on any S3-compatible object store.

    Works with:
    - AWS S3 (endpoint_url=None)
    - Cloudflare R2 (set endpoint_url to your R2 endpoint)
    - MinIO (set endpoint_url to your MinIO server)
    """

    def __init__(
        self,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "",
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.region = region or None
        self.endpoint_url = endpoint_url or None
        self._session = aioboto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=self.region,
        )

    def _object_key(self, matter_id: str, filename: str) -> str:
        """Build an S3 object key mimicking the local path structure."""
        safe_name = f"{hash(filename)}_{filename}"
        return f"matters/{matter_id}/{safe_name}"

    def _matter_prefix(self, matter_id: str) -> str:
        """Return the object-key prefix for a matter's files."""
        return f"matters/{matter_id}/"

    async def save(self, matter_id: str, filename: str, content: bytes) -> str:
        """Upload a file to S3 and return the object key (storage path)."""
        key = self._object_key(matter_id, filename)
        async with self._session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            await s3.put_object(Bucket=self.bucket_name, Key=key, Body=content)
        return key

    async def read(self, storage_path: str) -> bytes:
        """Download a file from S3 by its object key."""
        async with self._session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            response = await s3.get_object(Bucket=self.bucket_name, Key=storage_path)
            body = await response["Body"].read()
        return body

    async def delete(self, storage_path: str) -> None:
        """Delete a single object from S3."""
        async with self._session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            await s3.delete_object(Bucket=self.bucket_name, Key=storage_path)

    async def delete_matter_dir(self, matter_id: str) -> None:
        """Delete all objects under the matter's key prefix."""
        prefix = self._matter_prefix(matter_id)
        async with self._session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            async for page in pages:
                objects = page.get("Contents", [])
                if objects:
                    delete_keys = [{"Key": obj["Key"]} for obj in objects]
                    await s3.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={"Objects": delete_keys},
                    )

    async def get_matter_usage_bytes(self, matter_id: str) -> int:
        """Sum the sizes of all objects under the matter's key prefix."""
        prefix = self._matter_prefix(matter_id)
        total = 0
        async with self._session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            async for page in pages:
                for obj in page.get("Contents", []):
                    total += obj["Size"]
        return total
