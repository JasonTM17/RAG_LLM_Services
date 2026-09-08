"""Security abuse tests for document upload validation."""

from __future__ import annotations

import pytest

from rag_llm_services_api.application.document_service import (
    sanitize_filename,
    sniff_and_validate_mime,
)
from rag_llm_services_api.core.errors import (
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from rag_llm_services_api.infrastructure.storage.base import StreamHasher


def test_upload_rejects_path_traversal_filename() -> None:
    with pytest.raises(ValidationError) as excinfo:
        sanitize_filename("../../secrets.txt")

    assert excinfo.value.code == "INVALID_FILENAME"


def test_upload_rejects_oversized_stream_before_storage() -> None:
    hasher = StreamHasher(max_size_bytes=4)
    hasher.update(b"safe")

    with pytest.raises(PayloadTooLargeError) as excinfo:
        hasher.update(b"x")

    assert excinfo.value.code == "FILE_TOO_LARGE"


def test_upload_rejects_binary_document_disguised_as_text() -> None:
    with pytest.raises(UnsupportedMediaTypeError) as excinfo:
        sniff_and_validate_mime("notes.txt", b"%PDF-1.7\npretend text")

    assert excinfo.value.status_code == 415


def test_upload_rejects_pdf_extension_with_non_pdf_content() -> None:
    with pytest.raises(UnsupportedMediaTypeError) as excinfo:
        sniff_and_validate_mime("report.pdf", b"plain UTF-8 content")

    assert excinfo.value.status_code == 415


def test_upload_rejects_unsupported_executable_extension() -> None:
    with pytest.raises(UnsupportedMediaTypeError) as excinfo:
        sniff_and_validate_mime("helper.exe", b"MZ\x90\x00")

    assert excinfo.value.status_code == 415
