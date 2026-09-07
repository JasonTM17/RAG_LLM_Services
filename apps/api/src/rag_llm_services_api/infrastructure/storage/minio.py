"""MinIO object storage adapter with async offload and AppError mapping."""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncIterator
from typing import BinaryIO
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import HTTPError

from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.errors import (
    AppError,
    NotFoundError,
    UpstreamUnavailableError,
)
from rag_llm_services_api.infrastructure.storage.base import ObjectStoragePort

logger = logging.getLogger(__name__)


def _clean_endpoint(endpoint_url: str) -> tuple[str, bool]:
    """Extract host[:port] and secure flag from an endpoint string."""
    endpoint_stripped = endpoint_url.strip()
    if "://" in endpoint_stripped:
        parsed = urlparse(endpoint_stripped)
        secure = parsed.scheme == "https"
        host = parsed.netloc or parsed.path
    else:
        secure = False
        host = endpoint_stripped
    return host, secure


class MinIOObjectStorage(ObjectStoragePort):
    """MinIO implementation of ObjectStoragePort."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool | None = None,
    ) -> None:
        clean_host, detected_secure = _clean_endpoint(endpoint)
        is_secure = detected_secure if secure is None else secure
        self.bucket_name = bucket_name
        self._client = Minio(
            endpoint=clean_host,
            access_key=access_key,
            secret_key=secret_key,
            secure=is_secure,
        )

    def _map_error(self, exc: Exception, object_key: str | None = None) -> AppError:
        """Map storage exceptions to domain AppError types."""
        if isinstance(exc, S3Error):
            if exc.code in ("NoSuchKey", "NoSuchBucket"):
                target = f" '{object_key}'" if object_key else ""
                return NotFoundError(f"Storage object{target} not found")
            logger.error("MinIO S3Error: code=%s, message=%s", exc.code, exc.message)
            return AppError(f"Storage error: {exc.code}", code="STORAGE_ERROR", status_code=500)
        if isinstance(exc, (HTTPError, ConnectionError, OSError)):
            logger.error("MinIO upstream connection error: %s", exc)
            return UpstreamUnavailableError("Object storage service is unavailable")
        logger.error("Unexpected storage error: %s", exc)
        return AppError("Storage operation failed", code="STORAGE_ERROR", status_code=500)

    async def ensure_bucket_exists(self) -> None:
        """Ensure the target bucket exists, creating it if needed."""

        def _check_and_make() -> None:
            if not self._client.bucket_exists(self.bucket_name):
                self._client.make_bucket(self.bucket_name)

        try:
            await asyncio.to_thread(_check_and_make)
        except Exception as exc:
            raise self._map_error(exc) from exc

    async def put_object(
        self,
        object_key: str,
        data: bytes | BinaryIO,
        length: int,
        content_type: str,
    ) -> None:
        """Write raw bytes to object storage."""
        data_stream: BinaryIO = io.BytesIO(data) if isinstance(data, bytes) else data

        def _sync_put() -> None:
            self._client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
                data=data_stream,
                length=length,
                content_type=content_type,
            )

        try:
            await asyncio.to_thread(_sync_put)
        except Exception as exc:
            raise self._map_error(exc, object_key) from exc

    async def get_object(self, object_key: str) -> bytes:
        """Fetch full raw bytes from object storage."""

        def _sync_get() -> bytes:
            response = self._client.get_object(self.bucket_name, object_key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_sync_get)
        except Exception as exc:
            raise self._map_error(exc, object_key) from exc

    async def get_object_stream(
        self, object_key: str, chunk_size: int = 65536
    ) -> AsyncIterator[bytes]:
        """Stream raw bytes from object storage."""
        raw_bytes = await self.get_object(object_key)
        for i in range(0, len(raw_bytes), chunk_size):
            yield raw_bytes[i : i + chunk_size]

    async def delete_object(self, object_key: str) -> None:
        """Delete an object from object storage."""

        def _sync_delete() -> None:
            self._client.remove_object(self.bucket_name, object_key)

        try:
            await asyncio.to_thread(_sync_delete)
        except Exception as exc:
            raise self._map_error(exc, object_key) from exc

    async def object_exists(self, object_key: str) -> bool:
        """Check whether an object exists in storage."""

        def _sync_stat() -> bool:
            try:
                self._client.stat_object(self.bucket_name, object_key)
                return True
            except S3Error as err:
                if err.code in ("NoSuchKey", "NoSuchBucket"):
                    return False
                raise

        try:
            return await asyncio.to_thread(_sync_stat)
        except Exception as exc:
            raise self._map_error(exc, object_key) from exc


_storage_singleton: ObjectStoragePort | None = None


def get_object_storage(settings: Settings | None = None) -> ObjectStoragePort:
    """Dependency / accessor for the configured ObjectStoragePort."""
    global _storage_singleton
    if _storage_singleton is None:
        cfg = settings if settings is not None else get_settings()
        _storage_singleton = MinIOObjectStorage(
            endpoint=cfg.minio.endpoint,
            access_key=cfg.minio.access_key,
            secret_key=cfg.minio.secret_key,
            bucket_name=cfg.minio.bucket,
        )
    return _storage_singleton


def set_object_storage(storage: ObjectStoragePort | None) -> None:
    """Override or reset object storage for tests."""
    global _storage_singleton
    _storage_singleton = storage
