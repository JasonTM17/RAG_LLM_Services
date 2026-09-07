"""Unit tests for document upload validation, MIME sniffing, and object storage."""

from __future__ import annotations

import hashlib
import io
import uuid
import zipfile

import pytest
from minio.error import S3Error
from urllib3.exceptions import HTTPError

from rag_llm_services_api.application.document_service import (
    sanitize_filename,
    sniff_and_validate_mime,
)
from rag_llm_services_api.core.errors import (
    AppError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    UpstreamUnavailableError,
    ValidationError,
)
from rag_llm_services_api.infrastructure.storage.base import (
    StreamHasher,
    format_object_key,
    validate_object_key,
)
from rag_llm_services_api.infrastructure.storage.minio import MinIOObjectStorage


def _create_minimal_docx() -> bytes:
    """Helper creating a minimal valid DOCX zip package in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", b'<?xml version="1.0"?><Types/>')
        zf.writestr("word/document.xml", b'<?xml version="1.0"?><w:document/>')
    return buf.getvalue()


# -------------------------------------------------------------------------
# Filename sanitization & path traversal tests
# -------------------------------------------------------------------------


def test_sanitize_filename_valid() -> None:
    assert sanitize_filename("sample.pdf") == "sample.pdf"
    assert sanitize_filename("my notes 2026.txt") == "my notes 2026.txt"
    assert sanitize_filename("deep-learning.docx") == "deep-learning.docx"


def test_sanitize_filename_strips_nested_folders() -> None:
    assert sanitize_filename("folder/subfolder/document.pdf") == "document.pdf"
    assert sanitize_filename("nested\\path\\notes.txt") == "notes.txt"


@pytest.mark.parametrize(
    "malicious_filename",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\cmd.exe",
        "docs/../../secret.pdf",
        "..",
        "../test.txt",
        "nested/../../secret.txt",
    ],
)
def test_sanitize_filename_rejects_path_traversal(malicious_filename: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        sanitize_filename(malicious_filename)
    assert exc_info.value.code == "INVALID_FILENAME"


def test_sanitize_filename_rejects_empty_and_whitespace() -> None:
    with pytest.raises(ValidationError):
        sanitize_filename("")
    with pytest.raises(ValidationError):
        sanitize_filename("    ")


def test_sanitize_filename_rejects_null_bytes() -> None:
    with pytest.raises(ValidationError) as exc_info:
        sanitize_filename("test\x00payload.pdf")
    assert exc_info.value.code == "INVALID_FILENAME"


def test_sanitize_filename_rejects_overly_long_name() -> None:
    long_name = "a" * 256 + ".pdf"
    with pytest.raises(ValidationError) as exc_info:
        sanitize_filename(long_name)
    assert exc_info.value.code == "INVALID_FILENAME"


# -------------------------------------------------------------------------
# MIME sniffing and format validation tests
# -------------------------------------------------------------------------


def test_sniff_and_validate_mime_pdf() -> None:
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    mime = sniff_and_validate_mime("report.pdf", pdf_bytes)
    assert mime == "application/pdf"


def test_sniff_and_validate_mime_txt() -> None:
    txt_bytes = "This is a simple plain text document with Unicode: \u0110\u1ea1i h\u1ecdc".encode(
        "utf-8"
    )
    mime = sniff_and_validate_mime("notes.txt", txt_bytes)
    assert mime == "text/plain"


def test_sniff_and_validate_mime_markdown() -> None:
    md_bytes = b"# Architecture\n\nThis document describes RAG services."
    mime = sniff_and_validate_mime("README.md", md_bytes)
    assert mime == "text/markdown"


def test_sniff_and_validate_mime_docx() -> None:
    docx_bytes = _create_minimal_docx()
    mime = sniff_and_validate_mime("thesis.docx", docx_bytes)
    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_sniff_and_validate_mime_rejects_fake_pdf() -> None:
    fake_pdf = b"Just plain text without PDF magic headers"
    with pytest.raises(UnsupportedMediaTypeError) as exc_info:
        sniff_and_validate_mime("fake.pdf", fake_pdf)
    assert exc_info.value.status_code == 415


def test_sniff_and_validate_mime_rejects_fake_docx() -> None:
    fake_docx = b"Plain text disguised as docx"
    with pytest.raises(UnsupportedMediaTypeError) as exc_info:
        sniff_and_validate_mime("fake.docx", fake_docx)
    assert exc_info.value.status_code == 415


def test_sniff_and_validate_mime_rejects_text_with_null_bytes() -> None:
    corrupted_txt = b"Hello\x00World"
    with pytest.raises(UnsupportedMediaTypeError) as exc_info:
        sniff_and_validate_mime("corrupted.txt", corrupted_txt)
    assert exc_info.value.status_code == 415


@pytest.mark.parametrize(
    "unsupported_filename,content",
    [
        ("script.py", b"print('hello')"),
        ("app.exe", b"MZ\x90\x00"),
        ("archive.tar.gz", b"\x1f\x8b\x08"),
        ("image.png", b"\x89PNG\r\n\x1a\n"),
    ],
)
def test_sniff_and_validate_mime_rejects_unsupported_extension(
    unsupported_filename: str, content: bytes
) -> None:
    with pytest.raises(UnsupportedMediaTypeError) as exc_info:
        sniff_and_validate_mime(unsupported_filename, content)
    assert exc_info.value.status_code == 415


# -------------------------------------------------------------------------
# Streaming SHA-256 and size limit tests
# -------------------------------------------------------------------------


def test_stream_hasher_computes_accurate_sha256() -> None:
    data = b"Streaming data in several chunks for checksum verification"
    hasher = StreamHasher(max_size_bytes=1024)
    hasher.update(data[:10])
    hasher.update(data[10:30])
    hasher.update(data[30:])

    expected = hashlib.sha256(data).hexdigest()
    assert hasher.hexdigest == expected
    assert hasher.total_bytes == len(data)


def test_stream_hasher_rejects_oversized_file() -> None:
    hasher = StreamHasher(max_size_bytes=50)
    hasher.update(b"a" * 30)
    with pytest.raises(PayloadTooLargeError) as exc_info:
        hasher.update(b"b" * 30)
    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "FILE_TOO_LARGE"


# -------------------------------------------------------------------------
# Safe object key formatting and validation tests
# -------------------------------------------------------------------------


def test_format_object_key_valid() -> None:
    kb_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    sha256_hex = hashlib.sha256(b"content").hexdigest()

    key = format_object_key(kb_id, doc_id, version_id, sha256_hex)
    expected = f"knowledge_bases/{kb_id}/documents/{doc_id}/{version_id}/{sha256_hex}.bin"
    assert key == expected
    assert validate_object_key(key) is True


def test_format_object_key_rejects_invalid_checksum() -> None:
    kb_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()

    with pytest.raises(ValidationError) as exc_info:
        format_object_key(kb_id, doc_id, version_id, "invalid-not-64-hex")
    assert exc_info.value.code == "INVALID_CHECKSUM"


def test_validate_object_key_rejects_path_traversal() -> None:
    assert (
        validate_object_key("knowledge_bases/../../documents/foo/bar/0123456789abcdef.bin") is False
    )
    assert validate_object_key("some/random/path.bin") is False


# -------------------------------------------------------------------------
# MinIO adapter error mapping tests
# -------------------------------------------------------------------------


def test_minio_storage_error_mapping() -> None:
    storage = MinIOObjectStorage(
        endpoint="http://localhost:9000",
        access_key="test-key",
        secret_key="test-secret",
        bucket_name="test-bucket",
    )

    from unittest.mock import MagicMock

    mock_resp = MagicMock()

    # NoSuchKey S3Error -> NotFoundError
    s3_not_found = S3Error(
        code="NoSuchKey",
        message="The specified key does not exist.",
        resource="/test/key",
        request_id="req-1",
        host_id="host-1",
        response=mock_resp,
    )
    app_err = storage._map_error(s3_not_found, object_key="test-key")
    assert isinstance(app_err, NotFoundError)
    assert app_err.status_code == 404

    # NoSuchBucket S3Error -> NotFoundError
    s3_bucket_not_found = S3Error(
        code="NoSuchBucket",
        message="The specified bucket does not exist.",
        resource="/test",
        request_id="req-2",
        host_id="host-2",
        response=mock_resp,
    )
    app_err_bucket = storage._map_error(s3_bucket_not_found)
    assert isinstance(app_err_bucket, NotFoundError)
    assert app_err_bucket.status_code == 404

    # HTTPError -> UpstreamUnavailableError
    conn_err = HTTPError("Connection refused")
    app_err_conn = storage._map_error(conn_err)
    assert isinstance(app_err_conn, UpstreamUnavailableError)
    assert app_err_conn.status_code == 503

    # Other generic S3Error -> AppError 500
    s3_generic = S3Error(
        code="InternalError",
        message="We encountered an internal error. Please try again.",
        resource="/test",
        request_id="req-3",
        host_id="host-3",
        response=mock_resp,
    )
    app_err_generic = storage._map_error(s3_generic)
    assert isinstance(app_err_generic, AppError)
    assert app_err_generic.status_code == 500
    assert app_err_generic.code == "STORAGE_ERROR"
