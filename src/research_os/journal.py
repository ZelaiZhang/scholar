from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from research_os.io import atomic_write_text


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EVENT_KEYS = {
    "sequence",
    "event_type",
    "run_id",
    "created_at",
    "actor",
    "artifact_path",
    "artifact_hash",
    "summary",
    "previous_event_hash",
    "event_hash",
}


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    event_type: str
    run_id: str
    created_at: str
    actor: str
    artifact_path: str
    artifact_hash: str
    summary: str
    previous_event_hash: str
    event_hash: str


def _canonical(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _event_hash(payload: dict[str, object]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "event_hash"}
    return hashlib.sha256(_canonical(unsigned).encode("utf-8")).hexdigest()


def _parse_rows(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    if not path.exists():
        return [], []
    rows: list[dict[str, object]] = []
    issues: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            issues.append(f"研究日志第 {line_number} 行为空")
            continue
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            issues.append(f"研究日志第 {line_number} 行损坏：不是合法 JSON")
            continue
        if not isinstance(decoded, dict):
            issues.append(f"研究日志第 {line_number} 行损坏：必须是对象")
            continue
        rows.append(decoded)
    return rows, issues


def validate_journal(path: Path, *, project_root: Path) -> tuple[str, ...]:
    rows, issues = _parse_rows(path)
    root = project_root.resolve()
    previous = ""
    for index, row in enumerate(rows, 1):
        line_number = index
        keys = set(row)
        if keys != EVENT_KEYS:
            issues.append(
                f"研究日志第 {line_number} 行字段损坏："
                f"缺少 {sorted(EVENT_KEYS - keys)}，多出 {sorted(keys - EVENT_KEYS)}"
            )
        sequence = row.get("sequence")
        if sequence != index:
            issues.append(
                f"研究日志第 {line_number} 行序号无效：期望 {index}，实际 {sequence}"
            )
        current_previous = row.get("previous_event_hash")
        if current_previous != previous:
            issues.append(f"研究日志第 {line_number} 行前序哈希不匹配")
        stored_hash = row.get("event_hash")
        if not isinstance(stored_hash, str) or not HASH_PATTERN.fullmatch(
            stored_hash
        ):
            issues.append(f"研究日志第 {line_number} 行事件哈希格式无效")
        elif stored_hash != _event_hash(row):
            issues.append(f"研究日志第 {line_number} 行事件哈希校验失败")
        artifact_hash = row.get("artifact_hash")
        if not isinstance(artifact_hash, str) or not HASH_PATTERN.fullmatch(
            artifact_hash
        ):
            issues.append(f"研究日志第 {line_number} 行产物哈希格式无效")
        artifact_path = row.get("artifact_path")
        if not isinstance(artifact_path, str) or not artifact_path.strip():
            issues.append(f"研究日志第 {line_number} 行产物路径无效")
        else:
            try:
                artifact = (root / artifact_path).resolve()
                artifact.relative_to(root)
                if not artifact.is_file():
                    issues.append(
                        f"research journal line {line_number} artifact is missing: "
                        f"{artifact_path}"
                    )
            except (OSError, ValueError):
                issues.append(
                    f"研究日志第 {line_number} 行产物路径越出课题目录"
                )
        for field in ("event_type", "run_id", "created_at", "actor", "summary"):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                issues.append(f"研究日志第 {line_number} 行 {field} 无效")
        run_id = row.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            if not (root / "cycles" / run_id).is_dir():
                issues.append(
                    f"research journal line {line_number} references a missing run: "
                    f"{run_id}"
                )
        previous = stored_hash if isinstance(stored_hash, str) else ""
    return tuple(issues)


def append_event(
    path: Path,
    *,
    event_type: str,
    run_id: str,
    actor: str,
    artifact_path: str,
    artifact_hash: str,
    summary: str,
) -> JournalEvent:
    project_root = path.parent.resolve()
    existing_issues = validate_journal(path, project_root=project_root)
    if existing_issues:
        raise ValueError("研究日志损坏，拒绝追加: " + "; ".join(existing_issues))
    rows, _ = _parse_rows(path)
    previous = str(rows[-1]["event_hash"]) if rows else ""
    payload: dict[str, object] = {
        "sequence": len(rows) + 1,
        "event_type": event_type.strip(),
        "run_id": run_id.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "actor": actor.strip(),
        "artifact_path": artifact_path.strip().replace("\\", "/"),
        "artifact_hash": artifact_hash,
        "summary": summary.strip(),
        "previous_event_hash": previous,
    }
    for field in ("event_type", "run_id", "actor", "artifact_path", "summary"):
        if not payload[field]:
            raise ValueError(f"研究日志字段不能为空: {field}")
    if not HASH_PATTERN.fullmatch(artifact_hash):
        raise ValueError("artifact_hash 必须是 64 位小写十六进制字符串")
    payload["event_hash"] = _event_hash(payload)
    event = JournalEvent(**payload)  # type: ignore[arg-type]
    serialized_rows = [
        json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows
    ]
    serialized_rows.append(
        json.dumps(asdict(event), ensure_ascii=False, sort_keys=True)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = path.parent.stat()
    atomic_write_text(
        path,
        "\n".join(serialized_rows) + "\n",
        expected_parent_identity=(metadata.st_dev, metadata.st_ino),
    )
    return event
