"""Object storage port interface, safe key formatting, and streaming hash utilities."""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import BinaryIO
from uuid import UUID

from rag_llm_services_api.core.errors import PayloadTooLargeError, ValidationError
from rag_llm_services_api.domain.documents import DEFAULT_MAX_UPLOAD_SIZE_BYTES

_HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_OBJECT_KEY_PATTERN = re.compile(
    r"^knowledge_bases/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"documents/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"[0-9a-f]{64}\.bin$"
)


def format_object_key(
    kb_id: UUID | str,
    doc_id: UUID | str,
    version_id: UUID | str,
    sha256_hex: str,
) -> str:
    """Format safe object key: knowledge_bases/{kb_id}/documents/{doc_id}/{version_id}/{sha256}.bin.

    Enforces strict UUID types and 64-char lowercase hex checksum to prevent
    path traversal and unsafe key naming.
    """
    kb_uuid = kb_id if isinstance(kb_id, UUID) else UUID(str(kb_id))
    doc_uuid = doc_id if isinstance(doc_id, UUID) else UUID(str(doc_id))
    ver_uuid = version_id if isinstance(version_id, UUID) else UUID(str(version_id))

    sha_clean = sha256_hex.strip().lower()
    if not _HEX_64_PATTERN.match(sha_clean):
        raise ValidationError(
            "Invalid SHA-256 checksum format for storage key",
            code="INVALID_CHECKSUM",
        )

    key = f"knowledge_bases/{kb_uuid}/documents/{doc_uuid}/{ver_uuid}/{sha_clean}.bin"
    if not _OBJECT_KEY_PATTERN.match(key):
        raise ValidationError("Generated storage key failed invariant check")
    return key


def validate_object_key(key: str) -> bool:
    """Check if the given object key strictly matches the expected safe pattern."""
    return bool(_OBJECT_KEY_PATTERN.match(key))


class StreamHasher:
    """Streaming SHA-256 calculator with enforced maximum byte size limit."""

    def __init__(self, max_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES) -> None:
        self._hasher = hashlib.sha256()
        self._total_bytes = 0
        self._max_size_bytes = max_size_bytes

    def update(self, chunk: bytes) -> None:
        """Feed a chunk into the hash and size accumulator."""
        self._total_bytes += len(chunk)
        if self._total_bytes > self._max_size_bytes:
            raise PayloadTooLargeError(
                f"File size exceeds maximum allowed limit of {self._max_size_bytes} bytes",
                code="FILE_TOO_LARGE",
                status_code=413,
            )
        self._hasher.update(chunk)

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def hexdigest(self) -> str:
        return self._hasher.hexdigest()


class ObjectStoragePort(ABC):
    """Port interface for raw document object storage."""

    @abstractmethod
    async def put_object(
        self,
        object_key: str,
        data: bytes | BinaryIO,
        length: int,
        content_type: str,
    ) -> None:
        """Write raw bytes to object storage under the given object key."""
        ...

    @abstractmethod
    async def get_object(self, object_key: str) -> bytes:
        """Fetch raw bytes from object storage for the given object key."""
        ...

    @abstractmethod
    def get_object_stream(self, object_key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """Stream raw bytes from object storage."""
        ...

    @abstractmethod
    async def delete_object(self, object_key: str) -> None:
        """Delete an object from object storage."""
        ...

    @abstractmethod
    async def object_exists(self, object_key: str) -> bool:
        """Check whether an object exists in storage."""
        ...

    @abstractmethod
    async def ensure_bucket_exists(self) -> None:
        """Ensure the target bucket exists, creating it if necessary."""
        ...
