from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskFacts:
    stale_source_ids: tuple[str, ...]
    ledger_issue_codes: tuple[str, ...]
    cycle_state: str
    human_decision_required: bool
    profile_domains: tuple[str, ...]
    profile_tracks: tuple[str, ...]
    experiment_design_status: str


@dataclass(frozen=True)
class DashboardRisk:
    code: str
    severity: str
    state: str
    message: str
    trigger: str


def evaluate_dashboard_risks(facts: RiskFacts) -> tuple[DashboardRisk, ...]:
    risks: list[DashboardRisk] = []
    if facts.stale_source_ids:
        joined = ", ".join(facts.stale_source_ids)
        risks.append(
            DashboardRisk(
                code="EVIDENCE_SOURCE_STALE",
                severity="blocking",
                state="observed",
                message="课题关联了未登记、已移动或内容发生变化的来源。",
                trigger=f"stale_or_unknown_source_ids={joined}",
            )
        )
    if "missing_locator" in facts.ledger_issue_codes:
        risks.append(
            DashboardRisk(
                code="EVIDENCE_LOCATOR_MISSING",
                severity="blocking",
                state="observed",
                message="证据账本包含缺少页码、章节或段落定位的来源。",
                trigger="ledger_issue_codes contains missing_locator",
            )
        )
    remaining_codes = tuple(
        code
        for code in facts.ledger_issue_codes
        if code != "missing_locator"
    )
    if remaining_codes:
        risks.append(
            DashboardRisk(
                code="EVIDENCE_LEDGER_INVALID",
                severity="blocking",
                state="observed",
                message="证据账本存在结构、核验状态或来源关联问题。",
                trigger="ledger_issue_codes=" + ",".join(remaining_codes),
            )
        )
    if facts.cycle_state == "blocked":
        risks.append(
            DashboardRisk(
                code="RESEARCH_CYCLE_BLOCKED",
                severity="blocking",
                state="observed",
                message="当前科研循环处于受阻状态，不能安全推进。",
                trigger="cycle_state=blocked",
            )
        )
    if facts.human_decision_required:
        risks.append(
            DashboardRisk(
                code="HUMAN_IDEA_DECISION_PENDING",
                severity="attention",
                state="observed",
                message="独立评审已经完成，必须由研究者批准或拒绝 Idea。",
                trigger="cycle_state=awaiting_human_decision",
            )
        )
    if (
        "medical-ai" in facts.profile_domains
        and facts.experiment_design_status != "已产出"
    ):
        risks.append(
            DashboardRisk(
                code="MEDICAL_DESIGN_GATE_INCOMPLETE",
                severity="attention",
                state="missing_required",
                message="医疗 AI 课题尚未完成实验设计门禁，不能声称具体临床评价风险已被控制。",
                trigger=(
                    "profile.domains contains medical-ai; "
                    f"experiment_design_status={facts.experiment_design_status}"
                ),
            )
        )
    adaptation_tracks = tuple(
        track
        for track in facts.profile_tracks
        if track in {"finetuning", "quantization", "preference-optimization"}
    )
    if adaptation_tracks and facts.experiment_design_status != "已产出":
        risks.append(
            DashboardRisk(
                code="MODEL_ADAPTATION_DESIGN_INCOMPLETE",
                severity="attention",
                state="missing_required",
                message="模型适配课题尚未完成公平基线、资源披露与复现设计门禁。",
                trigger=(
                    "profile.tracks="
                    + ",".join(adaptation_tracks)
                    + "; experiment_design_status="
                    + facts.experiment_design_status
                ),
            )
        )
    return tuple(risks)
