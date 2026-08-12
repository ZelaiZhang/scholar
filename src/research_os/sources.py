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

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.startswith(
            "src-"
        ):
            raise ValueError("source_id 必须是以 src- 开头的字符串")
        if self.kind not in {"file", "doi", "arxiv", "url"}:
            raise ValueError(f"未知来源类型: {self.kind}")
        if not isinstance(self.canonical, str) or not self.canonical.strip():
            raise ValueError("canonical 必须是非空字符串")
        if not isinstance(self.imported_at, str) or not self.imported_at.strip():
            raise ValueError("imported_at 必须是非空字符串")
        if self.content_hash is not None and (
            not isinstance(self.content_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.content_hash)
        ):
            raise ValueError("content_hash 必须是 64 位十六进制字符串或 null")
        if self.kind == "file" and self.content_hash is None:
            raise ValueError("本地文件来源必须包含 content_hash")
        if not isinstance(self.notes, str):
            raise ValueError("notes 必须是字符串")
        if not isinstance(self.external_api_allowed, bool):
            raise ValueError("external_api_allowed 必须是布尔值")
        if not isinstance(self.metadata_status, str):
            raise ValueError("metadata_status 必须是字符串")


@dataclass(frozen=True)
class BatchAddResult:
    records: tuple[SourceRecord, ...]
    added: int
    duplicates: int
    authorizations_upgraded: int


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
    try:
        parsed_port = parts.port
    except ValueError as exc:
        raise InvalidSourceError(f"无效 URL 端口: {value}") from exc
    port = f":{parsed_port}" if parsed_port else ""
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


def load_source_manifest(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    manifest_path = path.resolve()
    values: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        candidate = Path(value).expanduser()
        is_identifier = value.lower().startswith(
            ("doi:", "arxiv:", "http://", "https://")
        )
        if not candidate.is_absolute() and not is_identifier:
            candidate = path.parent / candidate
            value = candidate.resolve().as_posix()
        if not is_identifier and Path(value).expanduser().resolve() == manifest_path:
            raise InvalidSourceError(
                f"{path}:{line_number}: 来源清单不能登记清单文件自身"
            )
        try:
            normalize_source(value)
        except InvalidSourceError as exc:
            raise InvalidSourceError(f"{path}:{line_number}: {exc}") from exc
        values.append(value)
    if not values:
        raise InvalidSourceError(f"来源清单没有可导入条目: {path}")
    return values


def _candidate_record(
    value: str, *, notes: str, external_api_allowed: bool
) -> SourceRecord:
    kind, canonical = normalize_source(value)
    content_hash = hash_file(Path(canonical)) if kind == "file" else None
    identity = content_hash if content_hash is not None else canonical
    return SourceRecord(
        source_id=make_source_id(kind, identity),
        kind=kind,
        canonical=canonical,
        imported_at=datetime.now(timezone.utc).isoformat(),
        content_hash=content_hash,
        notes=notes,
        external_api_allowed=external_api_allowed,
    )


class SourceRegistry:
    def __init__(
        self,
        path: Path,
        *,
        expected_parent_identity: tuple[int, int] | None = None,
    ):
        self.path = path
        self.expected_parent_identity = expected_parent_identity

    def _assert_parent_identity(self) -> None:
        if self.expected_parent_identity is None:
            return
        metadata = self.path.parent.stat()
        current_identity = (metadata.st_dev, metadata.st_ino)
        if current_identity != self.expected_parent_identity:
            raise OSError(
                f"来源登记目录在操作期间被替换: {self.path.parent}"
            )

    def _read(self) -> list[SourceRecord]:
        self._assert_parent_identity()
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
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"来源登记表第 {line_number} 行损坏: {self.path}"
                ) from exc
        return records

    def records(self) -> tuple[SourceRecord, ...]:
        return tuple(self._read())

    def verified_source_ids(self) -> set[str]:
        verified: set[str] = set()
        for record in self._read():
            if record.kind != "file":
                verified.add(record.source_id)
                continue
            path = Path(record.canonical)
            if (
                record.content_hash is not None
                and path.is_file()
                and hash_file(path) == record.content_hash
            ):
                verified.add(record.source_id)
        return verified

    def _write(self, records: list[SourceRecord]) -> None:
        self._assert_parent_identity()
        serialized = "\n".join(
            json.dumps(asdict(item), ensure_ascii=False, sort_keys=True)
            for item in records
        )
        atomic_write_text(
            self.path,
            f"{serialized}\n",
            expected_parent_identity=self.expected_parent_identity,
        )
        self._assert_parent_identity()

    def add(
        self,
        value: str,
        *,
        notes: str = "",
        external_api_allowed: bool = False,
    ) -> SourceRecord:
        return self.add_many(
            [value],
            notes=notes,
            external_api_allowed=external_api_allowed,
        ).records[0]

    def add_many(
        self,
        values: list[str],
        *,
        notes: str = "",
        external_api_allowed: bool = False,
    ) -> BatchAddResult:
        if not values:
            raise InvalidSourceError("批量来源不能为空")
        candidates = [
            _candidate_record(
                value,
                notes=notes,
                external_api_allowed=external_api_allowed,
            )
            for value in values
        ]
        records = self._read()
        indexes = {
            record.source_id: index for index, record in enumerate(records)
        }
        returned: list[SourceRecord] = []
        added = 0
        duplicates = 0
        upgraded = 0
        changed = False
        for candidate in candidates:
            index = indexes.get(candidate.source_id)
            if index is None:
                indexes[candidate.source_id] = len(records)
                records.append(candidate)
                returned.append(candidate)
                added += 1
                changed = True
                continue
            duplicates += 1
            existing = records[index]
            if (
                existing.kind == "file"
                and candidate.kind == "file"
                and existing.canonical != candidate.canonical
            ):
                existing = replace(existing, canonical=candidate.canonical)
                records[index] = existing
                changed = True
            if external_api_allowed and not existing.external_api_allowed:
                existing = replace(existing, external_api_allowed=True)
                records[index] = existing
                upgraded += 1
                changed = True
            returned.append(existing)
        if changed:
            self._write(records)
        return BatchAddResult(
            records=tuple(returned),
            added=added,
            duplicates=duplicates,
            authorizations_upgraded=upgraded,
        )


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


def load_authorized_external_texts(
    registry_path: Path,
    payload_files: list[Path],
    source_ids: list[str],
) -> tuple[str, ...]:
    authorized = authorize_external_sources(registry_path, source_ids)
    authorized_ids = {record.source_id for record in authorized}
    texts: list[str] = []
    for payload_file in payload_files:
        resolved = payload_file.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        raw = resolved.read_bytes()
        current_hash = hashlib.sha256(raw).hexdigest()
        current_id = make_source_id("file", current_hash)
        if current_id not in authorized_ids:
            raise SourceAuthorizationError(
                f"请求文件未被 source_id 授权: {resolved} ({current_id})"
            )
        try:
            texts.append(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise InvalidSourceError(f"外部模型文本必须是 UTF-8: {resolved}") from exc
    return tuple(texts)
