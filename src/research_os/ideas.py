from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import yaml

from research_os.io import (
    atomic_create_text,
    atomic_write_text,
    read_stable_direct_text,
)


IDEA_ID_PATTERN = re.compile(r"^idea-[0-9]{4}$")
SOURCE_ID_PATTERN = re.compile(r"^src-[a-z0-9]+$")
IDEA_STATUSES = {
    "draft",
    "needs_evidence",
    "needs_novelty_check",
    "reviewed",
    "shortlisted",
    "rejected",
    "selected",
}
AUTOMATED_TRANSITIONS = {
    "draft": {"needs_evidence", "needs_novelty_check", "rejected"},
    "needs_evidence": {"needs_novelty_check", "rejected"},
    "needs_novelty_check": {"reviewed", "rejected"},
    "reviewed": {"shortlisted", "rejected"},
    "shortlisted": {"rejected"},
    "rejected": set(),
    "selected": set(),
}
ARCHIVE_KEYS = {"schema_version", "project_slug", "ideas"}
IDEA_KEYS = {
    "idea_id",
    "parent_ids",
    "title",
    "scientific_question",
    "hypothesis",
    "contribution",
    "evidence_source_ids",
    "novelty",
    "scores",
    "method_risks",
    "medical_safety_risks",
    "failure_criterion",
    "external_experiment",
    "status",
    "generated_by_run",
    "provenance",
    "researcher_decision",
}
NOVELTY_KEYS = {
    "status",
    "queries",
    "nearest_source_ids",
    "differences",
    "unresolved_overlap",
}
SCORE_KEYS = {"interestingness", "novelty", "feasibility", "evidence_support"}
DECISION_KEYS = {"actor", "reason", "decided_at", "idea_hash"}


@dataclass(frozen=True)
class NoveltyEvidence:
    status: str
    queries: tuple[str, ...]
    nearest_source_ids: tuple[str, ...]
    differences: str
    unresolved_overlap: str


@dataclass(frozen=True)
class IdeaScores:
    interestingness: int
    novelty: int
    feasibility: int
    evidence_support: int


@dataclass(frozen=True)
class ResearcherDecision:
    actor: str
    reason: str
    decided_at: str
    idea_hash: str


@dataclass(frozen=True)
class IdeaRecord:
    idea_id: str
    parent_ids: tuple[str, ...]
    title: str
    scientific_question: str
    hypothesis: str
    contribution: str
    evidence_source_ids: tuple[str, ...]
    novelty: NoveltyEvidence
    scores: IdeaScores
    method_risks: tuple[str, ...]
    medical_safety_risks: tuple[str, ...]
    failure_criterion: str
    external_experiment: str
    status: str
    generated_by_run: str
    provenance: dict[str, object]
    researcher_decision: ResearcherDecision | None


@dataclass(frozen=True)
class IdeaArchive:
    schema_version: int
    project_slug: str
    ideas: tuple[IdeaRecord, ...]


def _require_exact_keys(
    raw: dict[str, object], expected: set[str], *, context: str
) -> None:
    actual = set(raw)
    if actual != expected:
        raise ValueError(
            f"{context} 字段无效：缺少 {sorted(expected - actual)}，"
            f"多出 {sorted(actual - expected)}"
        )


def _string(raw: object, *, context: str, allow_empty: bool = False) -> str:
    if not isinstance(raw, str) or (not allow_empty and not raw.strip()):
        raise ValueError(f"{context} 必须是{'可为空的' if allow_empty else '非空'}字符串")
    return raw.strip()


def _string_tuple(
    raw: object, *, context: str, allow_empty_items: bool = False
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{context} 必须是列表")
    values = tuple(
        _string(item, context=context, allow_empty=allow_empty_items) for item in raw
    )
    if len(values) != len(set(values)):
        raise ValueError(f"{context} 包含重复项")
    return values


def _parse_scores(raw: object) -> IdeaScores:
    if not isinstance(raw, dict):
        raise ValueError("Idea scores 必须是对象")
    _require_exact_keys(raw, SCORE_KEYS, context="Idea scores")
    values: dict[str, int] = {}
    for key in SCORE_KEYS:
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
            raise ValueError(f"Idea 分数 {key} 必须是 1 到 10 的整数")
        values[key] = value
    return IdeaScores(**values)


def _parse_novelty(raw: object) -> NoveltyEvidence:
    if not isinstance(raw, dict):
        raise ValueError("Idea novelty 必须是对象")
    _require_exact_keys(raw, NOVELTY_KEYS, context="Idea novelty")
    status = _string(raw["status"], context="novelty.status")
    if status not in {"pending", "checked", "search_failed"}:
        raise ValueError(f"未知 novelty.status: {status}")
    nearest = _string_tuple(
        raw["nearest_source_ids"], context="nearest_source_ids"
    )
    if any(not SOURCE_ID_PATTERN.fullmatch(item) for item in nearest):
        raise ValueError("nearest_source_ids 包含无效 source_id")
    return NoveltyEvidence(
        status=status,
        queries=_string_tuple(raw["queries"], context="novelty.queries"),
        nearest_source_ids=nearest,
        differences=_string(
            raw["differences"], context="novelty.differences", allow_empty=True
        ),
        unresolved_overlap=_string(
            raw["unresolved_overlap"],
            context="novelty.unresolved_overlap",
            allow_empty=True,
        ),
    )


def _parse_decision(raw: object) -> ResearcherDecision | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("researcher_decision 必须是对象或 null")
    _require_exact_keys(raw, DECISION_KEYS, context="researcher_decision")
    decision = ResearcherDecision(
        actor=_string(raw["actor"], context="decision.actor"),
        reason=_string(raw["reason"], context="decision.reason"),
        decided_at=_string(raw["decided_at"], context="decision.decided_at"),
        idea_hash=_string(raw["idea_hash"], context="decision.idea_hash"),
    )
    if decision.actor != "researcher":
        raise ValueError("Idea 批准 actor 必须是 researcher")
    if not re.fullmatch(r"[0-9a-f]{64}", decision.idea_hash):
        raise ValueError("Idea 批准内容哈希格式无效")
    return decision


def _parse_idea(raw: object) -> IdeaRecord:
    if not isinstance(raw, dict):
        raise ValueError("Idea 必须是对象")
    _require_exact_keys(raw, IDEA_KEYS, context="Idea")
    idea_id = _string(raw["idea_id"], context="idea_id")
    if not IDEA_ID_PATTERN.fullmatch(idea_id):
        raise ValueError(f"无效 idea_id: {idea_id}")
    parent_ids = _string_tuple(raw["parent_ids"], context="parent_ids")
    if any(not IDEA_ID_PATTERN.fullmatch(item) for item in parent_ids):
        raise ValueError("parent_ids 包含无效 idea_id")
    evidence_ids = _string_tuple(
        raw["evidence_source_ids"], context="evidence_source_ids"
    )
    if any(not SOURCE_ID_PATTERN.fullmatch(item) for item in evidence_ids):
        raise ValueError("evidence_source_ids 包含无效 source_id")
    risks = _string_tuple(raw["method_risks"], context="method_risks")
    safety = _string_tuple(
        raw["medical_safety_risks"], context="medical_safety_risks"
    )
    status = _string(raw["status"], context="status")
    if status not in IDEA_STATUSES:
        raise ValueError(f"未知 Idea 状态: {status}")
    provenance = raw["provenance"]
    if not isinstance(provenance, dict):
        raise ValueError("Idea provenance 必须是对象")
    record = IdeaRecord(
        idea_id=idea_id,
        parent_ids=parent_ids,
        title=_string(raw["title"], context="title"),
        scientific_question=_string(
            raw["scientific_question"], context="scientific_question"
        ),
        hypothesis=_string(raw["hypothesis"], context="hypothesis"),
        contribution=_string(raw["contribution"], context="contribution"),
        evidence_source_ids=evidence_ids,
        novelty=_parse_novelty(raw["novelty"]),
        scores=_parse_scores(raw["scores"]),
        method_risks=risks,
        medical_safety_risks=safety,
        failure_criterion=_string(
            raw["failure_criterion"], context="failure_criterion"
        ),
        external_experiment=_string(
            raw["external_experiment"], context="external_experiment"
        ),
        status=status,
        generated_by_run=_string(
            raw["generated_by_run"], context="generated_by_run"
        ),
        provenance=dict(provenance),
        researcher_decision=_parse_decision(raw["researcher_decision"]),
    )
    if record.status == "selected":
        if record.researcher_decision is None:
            raise ValueError("selected Idea 缺少人工批准")
        if record.researcher_decision.idea_hash != idea_content_hash(record):
            raise ValueError("selected Idea 的内容哈希与人工批准不一致")
    elif record.researcher_decision is not None:
        raise ValueError("非 selected Idea 不得包含 researcher_decision")
    return record


def _idea_payload(idea: IdeaRecord) -> dict[str, object]:
    payload = asdict(idea)
    payload["parent_ids"] = list(idea.parent_ids)
    payload["evidence_source_ids"] = list(idea.evidence_source_ids)
    payload["method_risks"] = list(idea.method_risks)
    payload["medical_safety_risks"] = list(idea.medical_safety_risks)
    payload["novelty"]["queries"] = list(idea.novelty.queries)  # type: ignore[index]
    payload["novelty"]["nearest_source_ids"] = list(  # type: ignore[index]
        idea.novelty.nearest_source_ids
    )
    return payload


def idea_content_hash(idea: IdeaRecord) -> str:
    payload = _idea_payload(idea)
    payload.pop("status", None)
    payload.pop("researcher_decision", None)
    payload.pop("provenance", None)
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_archive(
    archive: IdeaArchive, *, allowed_source_ids: set[str] | None = None
) -> None:
    if archive.schema_version != 1 or not archive.project_slug.strip():
        raise ValueError("Idea archive schema_version 或 project_slug 无效")
    ids = [idea.idea_id for idea in archive.ideas]
    if len(ids) != len(set(ids)):
        raise ValueError("Idea archive 包含重复 idea_id")
    selected_count = sum(idea.status == "selected" for idea in archive.ideas)
    if selected_count > 1:
        raise ValueError("Idea archive 只能有一个 selected Idea")
    if allowed_source_ids is not None:
        for idea in archive.ideas:
            referenced = set(idea.evidence_source_ids) | set(
                idea.novelty.nearest_source_ids
            )
            outside = sorted(referenced - allowed_source_ids)
            if outside:
                raise ValueError(
                    f"Idea {idea.idea_id} 引用了课题外来源: {', '.join(outside)}"
                )
    for idea in archive.ideas:
        parsed = _parse_idea(_idea_payload(idea))
        if parsed != idea:
            raise ValueError(f"Idea {idea.idea_id} 无法稳定序列化")


def load_idea_archive(
    path: Path,
    *,
    allowed_source_ids: set[str] | None = None,
    expected_parent: Path | None = None,
    expected_parent_identity: tuple[int, int] | None = None,
) -> IdeaArchive:
    try:
        raw = yaml.safe_load(
            read_stable_direct_text(
                path,
                expected_parent=expected_parent,
                expected_parent_identity=expected_parent_identity,
            )
        )
    except yaml.YAMLError as exc:
        raise ValueError(f"Idea archive YAML 损坏: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Idea archive 必须是对象")
    _require_exact_keys(raw, ARCHIVE_KEYS, context="Idea archive")
    if raw["schema_version"] != 1:
        raise ValueError("Idea archive schema_version 必须是 1")
    ideas_raw = raw["ideas"]
    if not isinstance(ideas_raw, list):
        raise ValueError("Idea archive ideas 必须是列表")
    archive = IdeaArchive(
        schema_version=1,
        project_slug=_string(raw["project_slug"], context="project_slug"),
        ideas=tuple(_parse_idea(item) for item in ideas_raw),
    )
    _validate_archive(archive, allowed_source_ids=allowed_source_ids)
    return archive


def save_idea_archive(
    path: Path,
    archive: IdeaArchive,
    *,
    overwrite: bool = True,
    expected_parent_identity: tuple[int, int] | None = None,
) -> None:
    _validate_archive(archive)
    payload = {
        "schema_version": archive.schema_version,
        "project_slug": archive.project_slug,
        "ideas": [_idea_payload(idea) for idea in archive.ideas],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = path.parent.stat()
    writer = atomic_write_text if overwrite else atomic_create_text
    writer(
        path,
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        expected_parent_identity=(
            expected_parent_identity
            if expected_parent_identity is not None
            else (metadata.st_dev, metadata.st_ino)
        ),
    )


def _replace_record(
    archive: IdeaArchive, idea_id: str, replacement: IdeaRecord
) -> IdeaArchive:
    if idea_id not in {idea.idea_id for idea in archive.ideas}:
        raise ValueError(f"Idea 不存在: {idea_id}")
    return replace(
        archive,
        ideas=tuple(
            replacement if idea.idea_id == idea_id else idea
            for idea in archive.ideas
        ),
    )


def transition_idea(
    archive: IdeaArchive, idea_id: str, new_status: str
) -> IdeaArchive:
    if new_status == "selected":
        raise ValueError("selected 状态只能通过人工批准产生")
    record = next(
        (idea for idea in archive.ideas if idea.idea_id == idea_id), None
    )
    if record is None:
        raise ValueError(f"Idea 不存在: {idea_id}")
    if new_status not in AUTOMATED_TRANSITIONS[record.status]:
        raise ValueError(f"非法 Idea 状态转换: {record.status} -> {new_status}")
    if new_status == "reviewed":
        if (
            record.novelty.status != "checked"
            or not record.novelty.queries
            or not record.novelty.nearest_source_ids
            or not record.novelty.differences
        ):
            raise ValueError("Idea 尚未完成可复核的新颖性检查")
    return _replace_record(archive, idea_id, replace(record, status=new_status))


def approve_idea(
    archive: IdeaArchive, idea_id: str, *, reason: str
) -> IdeaArchive:
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("人工批准理由不能为空")
    if any(idea.status == "selected" for idea in archive.ideas):
        raise ValueError("Idea archive 已有 selected Idea")
    record = next(
        (idea for idea in archive.ideas if idea.idea_id == idea_id), None
    )
    if record is None:
        raise ValueError(f"Idea 不存在: {idea_id}")
    if record.status != "shortlisted":
        raise ValueError("只有 shortlisted Idea 可以人工批准")
    if (
        record.novelty.status != "checked"
        or not record.novelty.queries
        or not record.novelty.nearest_source_ids
        or not record.novelty.differences
    ):
        raise ValueError(
            "shortlisted Idea must have a complete novelty check before approval"
        )
    decision = ResearcherDecision(
        actor="researcher",
        reason=clean_reason,
        decided_at=datetime.now(timezone.utc).isoformat(),
        idea_hash=idea_content_hash(record),
    )
    selected = replace(
        record, status="selected", researcher_decision=decision
    )
    return _replace_record(archive, idea_id, selected)
