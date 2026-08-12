from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class LedgerFormatError(ValueError):
    """Raised when an evidence ledger is not a YAML mapping."""


ALLOWED_TYPES = {"fact", "inference", "hypothesis"}
ALLOWED_STATUS = {"unverified", "partially_verified", "verified", "conflicted"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    claim_id: str
    message: str


def load_ledger(path: Path) -> dict[str, object]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LedgerFormatError(f"证据账本 YAML 无法解析: {exc}") from exc
    if not isinstance(loaded, dict):
        raise LedgerFormatError("证据账本顶层必须是 YAML mapping")
    claims = loaded.get("claims", [])
    if not isinstance(claims, list):
        raise LedgerFormatError("claims 必须是列表")
    return loaded


def validate_ledger(ledger: dict[str, object]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    raw_claims = ledger.get("claims", [])
    if not isinstance(raw_claims, list):
        return [ValidationIssue("invalid_claims", "<ledger>", "claims 必须是列表")]

    seen: set[str] = set()
    for index, raw_claim in enumerate(raw_claims, 1):
        if not isinstance(raw_claim, dict):
            issues.append(
                ValidationIssue(
                    "invalid_claim", f"item-{index}", "每个 claim 必须是 mapping"
                )
            )
            continue

        claim_id = str(raw_claim.get("claim_id", "")).strip() or f"item-{index}"
        if claim_id in seen:
            issues.append(
                ValidationIssue(
                    "duplicate_claim_id", claim_id, "claim_id 在账本中重复"
                )
            )
        seen.add(claim_id)

        if not str(raw_claim.get("statement", "")).strip():
            issues.append(
                ValidationIssue("missing_statement", claim_id, "claim 陈述不能为空")
            )

        claim_type = raw_claim.get("type")
        if claim_type not in ALLOWED_TYPES:
            issues.append(
                ValidationIssue(
                    "invalid_type",
                    claim_id,
                    "claim 类型必须是 fact、inference 或 hypothesis",
                )
            )

        status = raw_claim.get("status")
        if status not in ALLOWED_STATUS:
            issues.append(
                ValidationIssue("invalid_status", claim_id, "未知的证据核验状态")
            )

        if raw_claim.get("confidence") not in ALLOWED_CONFIDENCE:
            issues.append(
                ValidationIssue(
                    "invalid_confidence", claim_id, "置信度必须是 low、medium 或 high"
                )
            )

        if not str(raw_claim.get("limitations", "")).strip():
            issues.append(
                ValidationIssue(
                    "missing_limitations", claim_id, "必须明确陈述证据限制"
                )
            )

        support = raw_claim.get("support", [])
        if not isinstance(support, list):
            issues.append(
                ValidationIssue("invalid_support", claim_id, "support 必须是列表")
            )
            support = []

        if claim_type == "fact" and status == "verified" and not support:
            issues.append(
                ValidationIssue(
                    "missing_support", claim_id, "已核验事实至少需要一个支持来源"
                )
            )

        for source_index, source in enumerate(support, 1):
            if not isinstance(source, dict):
                issues.append(
                    ValidationIssue(
                        "invalid_source",
                        claim_id,
                        f"支持来源 {source_index} 必须是 mapping",
                    )
                )
                continue
            if not str(source.get("source_id", "")).strip():
                issues.append(
                    ValidationIssue(
                        "missing_source_id",
                        claim_id,
                        f"支持来源 {source_index} 缺少 source_id",
                    )
                )
            if claim_type == "fact" and status == "verified":
                if not str(source.get("locator", "")).strip():
                    issues.append(
                        ValidationIssue(
                            "missing_locator",
                            claim_id,
                            f"支持来源 {source_index} 缺少页码、章节或段落定位",
                        )
                    )
    return issues


def render_validation_report(
    ledger_path: Path, issues: list[ValidationIssue]
) -> str:
    lines = ["# 证据账本校验报告", "", f"- 文件：`{ledger_path}`"]
    if not issues:
        lines.extend(["- 状态：通过", "", "未发现结构或证据定位问题。"])
    else:
        lines.extend([f"- 状态：未通过（{len(issues)} 项）", "", "| Claim | 代码 | 问题 |", "|---|---|---|"])
        lines.extend(
            f"| {issue.claim_id} | {issue.code} | {issue.message} |"
            for issue in issues
        )
    return "\n".join(lines) + "\n"

