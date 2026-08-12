from pathlib import Path

import pytest

from research_os.pdf import InvalidPDFError, NeedsOCRError, extract_pdf


class Page:
    def __init__(self, text: str | None):
        self.text = text

    def extract_text(self) -> str | None:
        return self.text


class Reader:
    def __init__(self, _: str):
        self.pages = [Page("first"), Page("second")]


def test_extract_pdf_preserves_page_boundaries(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-test")

    result = extract_pdf(source, reader_factory=Reader)

    assert result.pages == ("first", "second")
    assert "<!-- page:1 -->" in result.markdown
    assert "<!-- page:2 -->" in result.markdown
    assert result.markdown.index("first") < result.markdown.index("second")


def test_extract_pdf_requests_ocr_for_image_only_document(tmp_path: Path) -> None:
    class EmptyReader:
        def __init__(self, _: str):
            self.pages = [Page(" "), Page(None)]

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-test")

    with pytest.raises(NeedsOCRError, match="OCR"):
        extract_pdf(source, reader_factory=EmptyReader)


def test_extract_pdf_rejects_non_pdf_extension(tmp_path: Path) -> None:
    source = tmp_path / "paper.txt"
    source.write_text("not a PDF", encoding="utf-8")

    with pytest.raises(InvalidPDFError):
        extract_pdf(source, reader_factory=Reader)


def test_extract_pdf_reports_reader_failure_without_guessing(tmp_path: Path) -> None:
    class BrokenReader:
        def __init__(self, _: str):
            raise RuntimeError("broken xref")

    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-test")

    with pytest.raises(InvalidPDFError, match="无法解析"):
        extract_pdf(source, reader_factory=BrokenReader)
