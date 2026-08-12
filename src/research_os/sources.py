from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from research_os.io import atomic_write_text


class InvalidSourceError(ValueError):
    """Raised when an input cannot be interpreted as a supported source."""


class SourceAuthorizationError(PermissionError):
    """Raised when a source is missing or not approved for external use."""


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

    def records(self) -> tuple[SourceRecord, ...]:
        return tuple(self._read())

    def _write(self, records: list[SourceRecord]) -> None:
        serialized = "\n".join(
            json.dumps(asdict(item), ensure_ascii=False, sort_keys=True)
            for item in records
        )
        atomic_write_text(self.path, f"{serialized}\n")

    def add(
        self,
        value: str,
        *,
        notes: str = "",
        external_api_allowed: bool = False,
    ) -> SourceRecord:
        kind, canonical = normalize_source(value)
        content_hash = hash_file(Path(canonical)) if kind == "file" else None
        identity = content_hash if content_hash is not None else canonical
        identifier = make_source_id(kind, identity)
        records = self._read()
        for index, record in enumerate(records):
            if record.source_id == identifier:
                if external_api_allowed and not record.external_api_allowed:
                    record = replace(record, external_api_allowed=True)
                    records[index] = record
                    self._write(records)
                return record

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
        self._write(records)
        return record


def authorize_external_sources(
    registry_path: Path, source_ids: list[str]
) -> tuple[SourceRecord, ...]:
    if not source_ids:
        raise SourceAuthorizationError("外部模型调用至少需要一个已授权 source_id")
    records = {
        record.source_id: record for record in SourceRegistry(registry_path).records()
    }
    authorized: list[SourceRecord] = []
    for identifier in source_ids:
        record = records.get(identifier)
        if record is None:
            raise SourceAuthorizationError(f"来源未登记: {identifier}")
        if not record.external_api_allowed:
            raise SourceAuthorizationError(f"来源未授权外发: {identifier}")
        authorized.append(record)
    return tuple(authorized)


def authorize_external_files(
    registry_path: Path,
    payload_files: list[Path],
    source_ids: list[str],
) -> tuple[SourceRecord, ...]:
    authorized = authorize_external_sources(registry_path, source_ids)
    authorized_ids = {record.source_id for record in authorized}
    for payload_file in payload_files:
        resolved = payload_file.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        current_id = make_source_id("file", hash_file(resolved))
        if current_id not in authorized_ids:
            raise SourceAuthorizationError(
                f"请求文件未被 source_id 授权: {resolved} ({current_id})"
            )
    return authorized
