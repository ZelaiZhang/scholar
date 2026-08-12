from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class InvalidPDFError(ValueError):
    """Raised when a PDF cannot be parsed safely."""


class NeedsOCRError(InvalidPDFError):
    """Raised when a PDF contains no extractable text."""


class PDFReader(Protocol):
    pages: object


@dataclass(frozen=True)
class ExtractedPDF:
    path: Path
    pages: tuple[str, ...]

    @property
    def markdown(self) -> str:
        sections = [
            f"<!-- page:{index} -->\n{text}"
            for index, text in enumerate(self.pages, 1)
        ]
        return f"# PDF 文本提取：{self.path.name}\n\n" + "\n\n".join(sections) + "\n"


def extract_pdf(
    path: Path,
    reader_factory: Callable[[str], PDFReader] | None = None,
) -> ExtractedPDF:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pdf":
        raise InvalidPDFError(f"文件扩展名不是 PDF: {path.name}")

    if reader_factory is None:
        from pypdf import PdfReader

        reader_factory = PdfReader

    try:
        reader = reader_factory(str(path))
        pages = tuple((page.extract_text() or "").strip() for page in reader.pages)
    except Exception as exc:
        raise InvalidPDFError(f"无法解析 PDF: {path.name}: {exc}") from exc

    if not any(pages):
        raise NeedsOCRError("PDF 没有可提取文本，请先进行 OCR 后再导入")
    return ExtractedPDF(path=path, pages=pages)

