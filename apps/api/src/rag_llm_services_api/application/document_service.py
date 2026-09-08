"""Application service for document uploads, validation, storage, and lifecycle."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import PurePosixPath
from uuid import UUID

import puremagic

from rag_llm_services_api.core.errors import (
    DuplicateDocumentError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from rag_llm_services_api.db.models.document import DocumentModel, DocumentVersionModel
from rag_llm_services_api.db.models.ingestion_job import IngestionJobModel
from rag_llm_services_api.domain.documents import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    DEFAULT_MAX_UPLOAD_SIZE_BYTES,
)
from rag_llm_services_api.infrastructure.repositories.documents import DocumentRepository
from rag_llm_services_api.infrastructure.repositories.knowledge_bases import KnowledgeBaseRepository
from rag_llm_services_api.infrastructure.storage.base import (
    ObjectStoragePort,
    StreamHasher,
    format_object_key,
)

logger = logging.getLogger(__name__)


def sanitize_filename(filename: str) -> str:
    """Sanitize and validate uploaded filename against path traversal and illegal characters."""
    if not filename or not filename.strip():
        raise ValidationError("Filename must not be empty", code="INVALID_FILENAME")
    if "\x00" in filename:
        raise ValidationError("Filename contains illegal null bytes", code="INVALID_FILENAME")

    normalized = filename.replace("\\", "/").strip()
    # Reject path traversal segments explicitly
    segments = [s.strip() for s in normalized.split("/") if s.strip()]
    if any(s in ("..", ".") for s in segments):
        raise ValidationError(
            "Path traversal characters are not permitted in filenames",
            code="INVALID_FILENAME",
        )

    safe_name = PurePosixPath(normalized).name
    if not safe_name or safe_name in (".", "..") or len(safe_name) > 255:
        raise ValidationError("Invalid filename format", code="INVALID_FILENAME")
    return safe_name


def sniff_and_validate_mime(filename: str, content: bytes) -> str:
    """Detect MIME type via puremagic and parser sniffing, rejecting unsupported formats."""
    safe_name = sanitize_filename(filename)
    lower_name = safe_name.lower()
    ext = PurePosixPath(lower_name).suffix

    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedMediaTypeError(
            f"File extension '{ext}' is not supported. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            code="UNSUPPORTED_MEDIA_TYPE",
            status_code=415,
        )

    detected: str | None = None
    try:
        detected = puremagic.from_string(content[:4096], mime=True)
    except (puremagic.PureError, ValueError, TypeError, OSError):
        detected = None

    # Normalization and sniff verification per file extension
    if ext == ".pdf":
        if content.startswith(b"%PDF-") or detected == "application/pdf":
            detected = "application/pdf"
        else:
            raise UnsupportedMediaTypeError(
                "File has .pdf extension but content is not a valid PDF",
                code="UNSUPPORTED_MEDIA_TYPE",
                status_code=415,
            )

    elif ext == ".docx":
        # DOCX is a zip package containing word/document.xml
        is_docx = False
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                namelist = zf.namelist()
                if "word/document.xml" in namelist or any(n.startswith("word/") for n in namelist):
                    is_docx = True
        except (zipfile.BadZipFile, KeyError, ValueError, OSError):
            is_docx = False

        if is_docx:
            detected = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            raise UnsupportedMediaTypeError(
                "File has .docx extension but is not a valid Word document package",
                code="UNSUPPORTED_MEDIA_TYPE",
                status_code=415,
            )

    elif ext in (".txt", ".md"):
        binary_document_mimes = {
            "application/pdf",
            "application/zip",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        if content.startswith((b"%PDF-", b"PK\x03\x04")) or detected in binary_document_mimes:
            raise UnsupportedMediaTypeError(
                "Text extension does not match detected binary document content",
                code="UNSUPPORTED_MEDIA_TYPE",
                status_code=415,
            )
        # Plain text / Markdown: verify valid UTF-8 and absence of null bytes
        if b"\x00" in content:
            raise UnsupportedMediaTypeError(
                "Text file contains binary null bytes",
                code="UNSUPPORTED_MEDIA_TYPE",
                status_code=415,
            )
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedMediaTypeError(
                "Text file must be valid UTF-8 encoded text",
                code="UNSUPPORTED_MEDIA_TYPE",
                status_code=415,
            ) from exc

        if ext == ".md":
            detected = "text/markdown"
        else:
            detected = "text/plain"

    if not detected or detected not in ALLOWED_MIME_TYPES:
        raise UnsupportedMediaTypeError(
            f"Unsupported MIME type: '{detected or 'unknown'}'. Allowed types: PDF, TXT, Markdown, DOCX",
            code="UNSUPPORTED_MEDIA_TYPE",
            status_code=415,
        )

    return detected


class DocumentApplicationService:
    """Orchestrates document upload, validation, MinIO storage, and database persistence."""

    def __init__(
        self,
        document_repo: DocumentRepository,
        knowledge_base_repo: KnowledgeBaseRepository,
        storage: ObjectStoragePort,
        max_upload_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES,
    ) -> None:
        self._doc_repo = document_repo
        self._kb_repo = knowledge_base_repo
        self._storage = storage
        self._max_upload_size_bytes = max_upload_size_bytes

    @property
    def max_upload_size_bytes(self) -> int:
        return self._max_upload_size_bytes

    async def upload_document(
        self,
        owner_id: UUID,
        knowledge_base_id: UUID,
        raw_filename: str,
        content: bytes,
        checksum_sha256: str | None = None,
    ) -> tuple[DocumentModel, DocumentVersionModel, IngestionJobModel]:
        """Validate upload, compute checksum, store in MinIO, and persist metadata."""
        # 1. Verify target knowledge base exists and belongs to owner
        kb = await self._kb_repo.get_by_id(owner_id, knowledge_base_id)
        if kb is None:
            raise NotFoundError("Target knowledge base not found")

        # 2. Sanitize filename
        safe_filename = sanitize_filename(raw_filename)

        # 3. Validate size
        file_size = len(content)
        if file_size == 0:
            raise ValidationError("Cannot upload empty file", code="EMPTY_FILE")
        if file_size > self._max_upload_size_bytes:
            raise PayloadTooLargeError(
                f"File size {file_size} exceeds maximum allowed {self._max_upload_size_bytes} bytes",
                code="FILE_TOO_LARGE",
                status_code=413,
            )

        # 4. MIME sniffing and content validation
        content_type = sniff_and_validate_mime(safe_filename, content)

        # 5. Checksum calculation (or reuse precomputed)
        if checksum_sha256 is None:
            hasher = StreamHasher(max_size_bytes=self._max_upload_size_bytes)
            hasher.update(content)
            computed_checksum = hasher.hexdigest
        else:
            computed_checksum = checksum_sha256

        # 6. Check duplicate checksum scoped to this knowledge base
        existing_version = await self._doc_repo.find_version_by_checksum(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            checksum_sha256=computed_checksum,
        )
        if existing_version is not None:
            raise DuplicateDocumentError(
                f"A document with checksum '{computed_checksum}' already exists in this knowledge base",
                code="DUPLICATE_DOCUMENT",
            )

        # 7. Generate IDs to format deterministic storage key matching DB record IDs
        import uuid

        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()
        storage_key = format_object_key(
            kb_id=knowledge_base_id,
            doc_id=doc_id,
            version_id=version_id,
            sha256_hex=computed_checksum,
        )

        # 8. Persist bytes to MinIO
        await self._storage.put_object(
            object_key=storage_key,
            data=content,
            length=file_size,
            content_type=content_type,
        )

        # 9. Persist database records using the exact matching IDs, cleaning up on failure
        try:
            doc, version, job = await self._doc_repo.create_document_with_version_and_job(
                document_id=doc_id,
                version_id=version_id,
                owner_id=owner_id,
                knowledge_base_id=knowledge_base_id,
                filename=safe_filename,
                content_type=content_type,
                file_size_bytes=file_size,
                checksum_sha256=computed_checksum,
                storage_key=storage_key,
            )
        except Exception:
            try:
                await self._storage.delete_object(storage_key)
            except Exception as cleanup_err:  # noqa: BLE001
                logger.warning(
                    "Failed to clean up storage object '%s' after DB failure: %s",
                    storage_key,
                    cleanup_err,
                )
            raise

        return doc, version, job

    async def get_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> DocumentModel:
        """Fetch document detail scoped to owner."""
        doc = await self._doc_repo.get_document_by_id(owner_id, document_id)
        if doc is None:
            raise NotFoundError("Document not found")
        return doc

    async def get_document_content(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> tuple[bytes, str, str]:
        """Fetch raw document content from storage, returning (bytes, content_type, filename)."""
        doc = await self.get_document(owner_id, document_id)
        if not doc.versions:
            raise NotFoundError("Document has no stored versions")

        # Select current version if specified, else highest version number
        target_version: DocumentVersionModel | None = None
        if doc.current_version_id is not None:
            for v in doc.versions:
                if v.id == doc.current_version_id:
                    target_version = v
                    break
        if target_version is None:
            target_version = max(doc.versions, key=lambda v: v.version_number)

        raw_bytes = await self._storage.get_object(target_version.storage_key)
        return raw_bytes, target_version.mime_type, doc.filename

    async def delete_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> None:
        """Delete document from database and purge objects from storage."""
        storage_keys = await self._doc_repo.delete_document(owner_id, document_id)
        if storage_keys is None:
            raise NotFoundError("Document not found")
        for key in storage_keys:
            try:
                await self._storage.delete_object(key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to delete storage object '%s': %s", key, exc)

    async def delete_storage_object(self, storage_key: str) -> None:
        """Purge a single object from storage."""
        try:
            await self._storage.delete_object(storage_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete storage object '%s': %s", storage_key, exc)

    async def reindex_document(
        self,
        owner_id: UUID,
        document_id: UUID,
    ) -> IngestionJobModel:
        """Trigger reindexing by creating a new IngestionJob."""
        doc = await self.get_document(owner_id, document_id)
        if not doc.versions:
            raise NotFoundError("Document has no stored versions to index")
        latest_version = doc.versions[-1]
        job = await self._doc_repo.create_ingestion_job(
            owner_id=owner_id,
            document_id=document_id,
            version_id=latest_version.id,
        )
        await self._doc_repo.update_document_status(owner_id, document_id, "UPLOADED")
        return job

    async def get_ingestion_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> IngestionJobModel:
        """Fetch ingestion job status scoped to owner."""
        job = await self._doc_repo.get_ingestion_job(owner_id, job_id)
        if job is None:
            raise NotFoundError("Ingestion job not found")
        return job
