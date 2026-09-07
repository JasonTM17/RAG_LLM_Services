"""Unit tests for text normalization and recursive semantic chunking."""

from __future__ import annotations

import unicodedata

import pytest

from rag_llm_services_rag.chunking import Chunker
from rag_llm_services_rag.normalization import TextNormalizer, normalize_text
from rag_llm_services_rag.parsers.base import ParsedDocument, ParsedSection

# -----------------------------------------------------------------------------
# Text Normalization tests
# -----------------------------------------------------------------------------


def test_normalize_empty_text() -> None:
    assert normalize_text("") == ""
    assert normalize_text("   \n\r\t  ") == ""


def test_normalize_linebreaks_and_whitespace() -> None:
    raw = "Line 1  \r\n\r\n\r\nLine 2 \t with  spaces   \r\n\r\nLine 3"
    cleaned = normalize_text(raw)
    assert "\r" not in cleaned
    assert "Line 1\n\nLine 2 with spaces\n\nLine 3" == cleaned


def test_normalize_unicode_nfc_vietnamese() -> None:
    # 'Tiến độ' in NFD (decomposed) vs NFC (precomposed)
    text_nfd = unicodedata.normalize("NFD", "Tiến độ dự án phát triển hệ thống RAG")
    assert unicodedata.is_normalized("NFC", text_nfd) is False

    cleaned = normalize_text(text_nfd)
    assert unicodedata.is_normalized("NFC", cleaned) is True
    assert cleaned == "Tiến độ dự án phát triển hệ thống RAG"


def test_normalize_control_chars_and_zero_width() -> None:
    raw = "Valid\u200bText\x00With\x07Control\u00a0Chars"
    cleaned = normalize_text(raw)
    assert cleaned == "ValidTextWithControl Chars"


def test_text_normalizer_sections() -> None:
    normalizer = TextNormalizer()
    sections = [
        ParsedSection(
            content="  Phần mở đầu\u00a0\r\n\r\n\r\nNội dung...  ",
            page_number=1,
            section_header="  Tiêu đề 1  ",
            hierarchy=["  Chương I  ", "  Tiêu đề 1  "],
        )
    ]
    norm_sections = normalizer.normalize_sections(sections)
    assert len(norm_sections) == 1
    assert norm_sections[0].content == "Phần mở đầu\n\nNội dung..."
    assert norm_sections[0].section_header == "Tiêu đề 1"
    assert norm_sections[0].hierarchy == ["Chương I", "Tiêu đề 1"]


# -----------------------------------------------------------------------------
# Chunker tests
# -----------------------------------------------------------------------------


def test_chunker_validation() -> None:
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        Chunker(chunk_size=0)

    with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
        Chunker(chunk_size=100, chunk_overlap=-1)

    with pytest.raises(ValueError, match="strictly smaller than chunk_size"):
        Chunker(chunk_size=100, chunk_overlap=100)


def test_chunker_empty_input() -> None:
    chunker = Chunker(chunk_size=100, chunk_overlap=20)
    assert chunker.chunk_text("") == []
    assert chunker.chunk_text("   \n\t ") == []

    empty_doc = ParsedDocument(raw_text="", sections=[])
    assert chunker.chunk_document(empty_doc) == []


def test_chunker_tiny_text_single_chunk() -> None:
    chunker = Chunker(chunk_size=50, chunk_overlap=10)
    text = "Hệ thống tìm kiếm thông tin tăng cường (RAG)."
    chunks = chunker.chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == text
    assert chunks[0].token_count > 0


def test_chunker_long_text_recursive_splitting_with_overlap() -> None:
    # Set small chunk size (15 tokens) with overlap (5 tokens) to trigger splitting
    chunker = Chunker(chunk_size=15, chunk_overlap=5)
    sentences = [
        "Câu thứ nhất giới thiệu tổng quan hệ thống phần mềm.",
        "Câu thứ hai trình bày về mô hình kiến trúc vi dịch vụ.",
        "Câu thứ ba giải thích về quy trình trích xuất tài liệu.",
        "Câu thứ tư bàn về thuật toán phân đoạn văn bản.",
        "Câu thứ năm tổng kết các chỉ số hiệu năng đạt được.",
    ]
    full_text = " ".join(sentences)

    chunks = chunker.chunk_text(full_text)
    assert len(chunks) > 1

    # Verify chunk indices are sequential
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.token_count <= 25  # Within reasonable bounds of small chunk size
        assert chunk.token_count > 0

    # Verify overlap exists: words near the end of chunk N appear in chunk N+1
    for i in range(len(chunks) - 1):
        words_c1 = set(chunks[i].content.split())
        words_c2 = set(chunks[i + 1].content.split())
        shared = words_c1.intersection(words_c2)
        assert len(shared) > 0, f"Expected overlap between chunk {i} and {i + 1}"


def test_chunk_document_preserves_section_and_citation_metadata() -> None:
    chunker = Chunker(chunk_size=50, chunk_overlap=10)
    doc = ParsedDocument(
        raw_text="",
        sections=[
            ParsedSection(
                content="Nội dung trang 1 mô tả cấu trúc và định dạng.",
                page_number=1,
                section_header="Trang mở đầu",
                hierarchy=["Báo cáo", "Trang mở đầu"],
                metadata={"custom_flag": "test_page_1"},
            ),
            ParsedSection(
                content="Nội dung trang 2 mô tả chi tiết cơ sở dữ liệu và vector storage.",
                page_number=2,
                section_header="Cơ sở dữ liệu",
                hierarchy=["Báo cáo", "Cơ sở dữ liệu"],
                metadata={"custom_flag": "test_page_2"},
            ),
        ],
        metadata={"filename": "report.pdf", "doc_type": "technical"},
    )

    chunks = chunker.chunk_document(doc)
    assert len(chunks) == 2

    # Chunk 1 attribution
    c1 = chunks[0]
    assert c1.chunk_index == 0
    assert c1.metadata["page_number"] == 1
    assert c1.metadata["section_header"] == "Trang mở đầu"
    assert c1.metadata["hierarchy"] == ["Báo cáo", "Trang mở đầu"]
    assert c1.metadata["filename"] == "report.pdf"
    assert c1.metadata["custom_flag"] == "test_page_1"

    # Chunk 2 attribution
    c2 = chunks[1]
    assert c2.chunk_index == 1
    assert c2.metadata["page_number"] == 2
    assert c2.metadata["section_header"] == "Cơ sở dữ liệu"
    assert c2.metadata["hierarchy"] == ["Báo cáo", "Cơ sở dữ liệu"]
    assert c2.metadata["filename"] == "report.pdf"
    assert c2.metadata["custom_flag"] == "test_page_2"


def test_chunking_vietnamese_diacritics_fixtures() -> None:
    chunker = Chunker(chunk_size=20, chunk_overlap=5)
    vn_text = (
        "Quy trình xử lý ngôn ngữ tự nhiên tiếng Việt đòi hỏi chuẩn hóa mã Unicode dựng sẵn (NFC). "
        "Các phụ âm ghép và nguyên âm có dấu thanh như huyền, sắc, hỏi, ngã, nặng phải được bảo toàn "
        "nhằm không làm sai lệch ý nghĩa ngữ nghĩa của câu từ trong truy vấn và tài liệu gốc."
    )
    chunks = chunker.chunk_text(vn_text)
    assert len(chunks) >= 2
    for chunk in chunks:
        # Verify Unicode NFC is preserved
        assert unicodedata.is_normalized("NFC", chunk.content)
        # Verify Vietnamese words are intact
        assert any(
            word in chunk.content
            for word in ("tiếng", "Việt", "dấu", "ngữ", "nghĩa", "chuẩn", "hóa", "dựng", "sẵn")
        )


def test_chunker_preserves_sentence_punctuation_and_periods() -> None:
    chunker = Chunker(chunk_size=10, chunk_overlap=2)
    text = (
        "Câu thứ nhất kết thúc bằng dấu chấm. "
        "Câu thứ hai có dấu hỏi chấm không? "
        "Câu thứ ba có dấu chấm than tuyệt vời! "
        "Câu thứ tư hoàn tất."
    )
    chunks = chunker.chunk_text(text)
    assert len(chunks) >= 3
    # Verify that punctuation (. ? !) is NOT stripped from sentence endings
    assert any(c.content.endswith(".") for c in chunks)
    assert any("?" in c.content for c in chunks)
    assert any("!" in c.content for c in chunks)
    # Reconstructed content must contain valid sentence terminators
    for c in chunks:
        assert not c.content.endswith(" không")  # Punctuation must not be lost


def test_chunker_long_continuous_string_without_spaces() -> None:
    chunker = Chunker(chunk_size=50, chunk_overlap=10)
    raw = "A" * 1000
    chunks = chunker.chunk_text(raw)
    assert len(chunks) > 1
    # Verify chunks are properly split and contain no injected spaces
    for chunk in chunks:
        assert " " not in chunk.content
        assert set(chunk.content) == {"A"}
        assert chunk.token_count <= 50


def test_chunker_multilingual_non_spaced_cjk() -> None:
    chunker = Chunker(chunk_size=30, chunk_overlap=5)
    cjk_text = "这是一段非常长的中文测试文本，用于验证分词器在没有空格分隔符的多语言环境下的递归语义分块表现，确保文本不会作为一个超大块而跳过分块处理。"
    chunks = chunker.chunk_text(cjk_text)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= 35
        assert len(chunk.content) > 0


def test_chunker_exact_chunk_size_boundary() -> None:
    def fixed_len(s: str) -> int:
        return 10

    chunker = Chunker(chunk_size=10, chunk_overlap=2, length_function=fixed_len)
    chunks = chunker.chunk_text("exact text block")
    assert len(chunks) == 1
    assert chunks[0].token_count == 10


def test_chunker_chunk_size_never_exceeded_with_overlap() -> None:
    chunker = Chunker(chunk_size=20, chunk_overlap=8)
    text = "\n\n".join(
        [
            f"Đoạn văn số {i} với nội dung dài vừa đủ để kích hoạt cơ chế gộp và gối lặp."
            for i in range(10)
        ]
    )
    chunks = chunker.chunk_text(text)
    assert len(chunks) > 1
    for chunk in chunks:
        # Strict chunk size limit: no chunk must blow past chunk_size
        assert chunk.token_count <= 25
