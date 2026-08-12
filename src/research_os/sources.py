from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from research_os.io import atomic_write_text


class InvalidSourceError(ValueError):
    """Raised when an input cannot be interpreted as a supported source."""


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    kind: str
    canonical: str
    imported_at: str
    content_hash: str | None = None
    notes: str = ""
    external_api_allowed: bool = False
    metadata_status: str = "unverified"


DOI_PATTERN = re.compile(
    r"^(?:(?:doi:)\s*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/\S+)$",
    re.IGNORECASE,
)
ARXIV_PREFIX_PATTERN = re.compile(r"^arxiv:\s*([^\s]+)$", re.IGNORECASE)
ARXIV_URL_PATTERN = re.compile(
    r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/([^?#]+?)(?:\.pdf)?$",
    re.IGNORECASE,
)


def _normalize_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise InvalidSourceError(f"无效 URL: {value}")
    hostname = (parts.hostname or "").lower()
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{hostname}{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


def normalize_source(value: str) -> tuple[str, str]:
    raw = value.strip()
    if not raw:
        raise InvalidSourceError("来源不能为空")

    doi_match = DOI_PATTERN.match(raw)
    if doi_match:
        return "doi", doi_match.group(1).rstrip(".,;)").lower()

    arxiv_match = ARXIV_PREFIX_PATTERN.match(raw) or ARXIV_URL_PATTERN.match(raw)
    if arxiv_match:
        identifier = arxiv_match.group(1).rstrip("/")
        if not identifier:
            raise InvalidSourceError(f"无效 arXiv 标识: {raw}")
        return "arxiv", identifier.lower()

    path = Path(raw).expanduser()
    if path.is_file():
        return "file", path.resolve().as_posix()

    if raw.lower().startswith(("http://", "https://")):
        return "url", _normalize_url(raw)

    raise InvalidSourceError(
        "来源必须是已存在的本地文件、DOI、arXiv 标识或 HTTP(S) URL"
    )


def make_source_id(kind: str, canonical: str) -> str:
    digest = hashlib.sha256(f"{kind}:{canonical}".encode("utf-8")).hexdigest()[:16]
    return f"src-{digest}"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SourceRegistry:
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> list[SourceRecord]:
        if not self.path.exists():
            return []
        records: list[SourceRecord] = []
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                records.append(SourceRecord(**json.loads(line)))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"来源登记表第 {line_number} 行损坏: {self.path}"
                ) from exc
        return records

    def add(
        self,
        value: str,
        *,
        notes: str = "",
        external_api_allowed: bool = False,
    ) -> SourceRecord:
        kind, canonical = normalize_source(value)
        identifier = make_source_id(kind, canonical)
        records = self._read()
        for record in records:
            if record.source_id == identifier:
                return record

        content_hash = hash_file(Path(canonical)) if kind == "file" else None
        record = SourceRecord(
            source_id=identifier,
            kind=kind,
            canonical=canonical,
            imported_at=datetime.now(timezone.utc).isoformat(),
            content_hash=content_hash,
            notes=notes,
            external_api_allowed=external_api_allowed,
        )
        records.append(record)
        serialized = "\n".join(
            json.dumps(asdict(item), ensure_ascii=False, sort_keys=True)
            for item in records
        )
        atomic_write_text(self.path, f"{serialized}\n")
        return record

