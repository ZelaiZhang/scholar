"""Installed-wheel smoke journey; run outside the repository source tree."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
from pathlib import Path

from research_os.cli import main
from research_os.cycle import advance_cycle
from research_os.doctor import EXPECTED_SKILLS
from research_os.ideas import (
    IdeaArchive,
    IdeaRecord,
    IdeaScores,
    NoveltyEvidence,
    save_idea_archive,
)
from research_os.project import link_project_sources
from research_os.sources import SourceRegistry


def run_cli(argv: list[str]) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        code = main(argv)
    return code, output.getvalue()


def workspace_bytes(workspace: Path) -> dict[str, bytes]:
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def main_smoke(workspace: Path, repository: Path) -> None:
    workspace.mkdir()
    for folder in ("projects", "library", "inbox", "config"):
        (workspace / folder).mkdir()
    shutil.copy2(repository / "config" / "research.yaml", workspace / "config")
    shutil.copy2(
        repository / "library" / "sources.jsonl",
        workspace / "library" / "sources.jsonl",
    )
    shutil.copytree(
        repository / "library" / "knowledge",
        workspace / "library" / "knowledge",
    )
    for skill in EXPECTED_SKILLS:
        destination = workspace / ".agents" / "skills" / skill
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(repository / ".agents" / "skills" / skill, destination)

    code, doctor = run_cli(["doctor", "--workspace", str(workspace)])
    assert code == 0, doctor
    code, created = run_cli(
        [
            "new-project",
            "--title",
            "Installed Wheel Topic",
            "--slug",
            "wheel-topic",
            "--workspace",
            str(workspace),
        ]
    )
    assert code == 0, created
    project = workspace / "projects" / "wheel-topic"
    (project / "knowledge-profile.yaml").write_text(
        "schema_version: 1\n"
        "domains: [medical-ai]\n"
        "tracks: [diagnostic-reasoning]\n"
        "study_type: diagnostic-accuracy-study\n"
        "data_modalities: [text]\n"
        "reporting_context: [diagnostic-accuracy]\n",
        encoding="utf-8",
    )
    code, kb_doctor = run_cli(["kb", "doctor", "--workspace", str(workspace)])
    assert code == 0 and "28 条目录" in kb_doctor, kb_doctor
    code, kb_search = run_cli(
        [
            "kb",
            "search",
            "diagnostic accuracy",
            "--topic",
            "medical-ai",
            "--format",
            "json",
            "--workspace",
            str(workspace),
        ]
    )
    assert code == 0, kb_search
    search_payload = json.loads(kb_search)
    assert search_payload and search_payload[0]["source_id"].startswith("src-")
    code, chinese_search = run_cli(
        [
            "kb",
            "search",
            "诊断准确性",
            "--format",
            "json",
            "--workspace",
            str(workspace),
        ]
    )
    assert code == 0, chinese_search
    chinese_payload = json.loads(chinese_search)
    assert "STARD-AI" in chinese_payload[0]["title"]
    assert "alias" in chinese_payload[0]["matched_fields"]
    project_before_gaps = (project / "project.yaml").read_bytes()
    gaps_args = [
        "kb",
        "gaps",
        "--as-of",
        "2026-08-12",
        "--format",
        "json",
        "--workspace",
        str(workspace),
    ]
    code, first_gaps = run_cli(gaps_args)
    assert code == 0, first_gaps
    code, second_gaps = run_cli(gaps_args)
    assert code == 0 and second_gaps == first_gaps, second_gaps
    gaps_payload = json.loads(first_gaps)
    assert gaps_payload and gaps_payload[0]["kind"] == "missing-card"
    assert (project / "project.yaml").read_bytes() == project_before_gaps
    code, kb_recommend = run_cli(
        [
            "kb",
            "recommend",
            "--project",
            "wheel-topic",
            "--format",
            "json",
            "--workspace",
            str(workspace),
        ]
    )
    assert code == 0, kb_recommend
    recommendations = json.loads(kb_recommend)
    assert 1 <= len(recommendations) <= 3
    assert any(item["kind"] == "reporting-guideline" for item in recommendations)
    source = SourceRegistry(workspace / "library" / "sources.jsonl").add(
        "doi:10.1000/wheel-smoke"
    )
    link_project_sources(workspace, "wheel-topic", [source.source_id])
    papers = workspace / "library" / "papers"
    papers.mkdir()
    (papers / f"{source.source_id}.md").write_text(
        f"# Smoke paper\n\nsource_id: {source.source_id}\nLocator: p. 1\n",
        encoding="utf-8",
    )
    (project / "00-research-brief.md").write_text(
        "# Installed Wheel Topic\n\nA falsifiable question.\n\n"
        "<!-- research-os:stage=brief-complete -->\n",
        encoding="utf-8",
    )
    (project / "02-evidence-ledger.yaml").write_text(
        "schema_version: 1\nproject: Installed Wheel Topic\nclaims:\n"
        "  - claim_id: C001\n    statement: Public smoke evidence.\n"
        "    type: fact\n    status: verified\n    support:\n"
        f"      - source_id: {source.source_id}\n        locator: p. 1\n"
        "    opposition: []\n    confidence: medium\n"
        "    limitations: Packaging smoke only.\n",
        encoding="utf-8",
    )
    (project / "03-literature-review.md").write_text(
        "# Literature review\n\nEvidence synthesized.\n\n"
        "<!-- research-os:stage=synthesis-complete -->\n",
        encoding="utf-8",
    )

    dashboard_args = [
        "dashboard",
        "--project",
        "wheel-topic",
        "--as-of",
        "2026-08-12",
        "--format",
        "json",
        "--workspace",
        str(workspace),
    ]
    dashboard_before = workspace_bytes(workspace)
    code, first_dashboard = run_cli(dashboard_args)
    assert code == 0, first_dashboard
    code, second_dashboard = run_cli(dashboard_args)
    assert code == 0 and second_dashboard == first_dashboard, second_dashboard
    dashboard_payload = json.loads(first_dashboard)
    assert dashboard_payload["schema_version"] == 1
    assert dashboard_payload["as_of"] == "2026-08-12"
    assert dashboard_payload["project"]["slug"] == "wheel-topic"
    assert len(dashboard_payload["actions"]) <= 3
    assert workspace_bytes(workspace) == dashboard_before

    cycle_args = ["cycle", "--project", "wheel-topic", "--workspace", str(workspace)]
    code, first = run_cli(cycle_args)
    assert code == 0 and "candidate_generation" in first, first
    code, resumed = run_cli(cycle_args)
    assert code == 0 and "candidate_generation" in resumed, resumed
    run_id = next(
        line.split(": ", 1)[1]
        for line in first.splitlines()
        if line.startswith("Run: ")
    )
    assert run_id in resumed
    run_dir = project / "cycles" / run_id
    assert "guidance-only" in (run_dir / "work-packet.md").read_text(encoding="utf-8")

    candidate = IdeaRecord(
        idea_id="idea-0001",
        parent_ids=(),
        title="Installed-wheel candidate",
        scientific_question="Does an evidence gate reduce unsupported conclusions?",
        hypothesis="The gate reduces unsupported conclusions.",
        contribution="A bounded, falsifiable guidance method.",
        evidence_source_ids=(source.source_id,),
        novelty=NoveltyEvidence(
            status="checked",
            queries=("evidence gate unsupported conclusions",),
            nearest_source_ids=(source.source_id,),
            differences="Requires an explicit counterevidence gate.",
            unresolved_overlap="",
        ),
        scores=IdeaScores(8, 7, 7, 6),
        method_risks=("Evaluation leakage",),
        medical_safety_risks=("No clinical utility claim",),
        failure_criterion="Unsupported conclusions do not decrease.",
        external_experiment="Run only in an independent experiment repository.",
        status="draft",
        generated_by_run=run_id,
        provenance={"fixture": "installed-wheel"},
        researcher_decision=None,
    )
    save_idea_archive(
        run_dir / "candidates.yaml", IdeaArchive(1, "wheel-topic", (candidate,))
    )
    assert advance_cycle(workspace, "wheel-topic").state == "independent_review"
    reviews = run_dir / "reviews"
    reviews.mkdir()
    assessment = {
        "idea_id": "idea-0001",
        "strengths": ["Falsifiable"],
        "concerns": ["Packaging fixture only"],
        "blocking_issues": [],
        "recommendation": "advance",
        "confidence": 4,
    }
    for role in ("novelty", "methods", "medical-safety"):
        (reviews / f"{role}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "role": role,
                    "assessments": [assessment],
                }
            ),
            encoding="utf-8",
        )
    assert advance_cycle(workspace, "wheel-topic").state == "meta_review"
    (run_dir / "meta-review.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "consensus": ["The candidate is testable"],
                "conflicts": [],
                "blocking_issues": [],
                "shortlist_ids": ["idea-0001"],
                "rationale_by_idea": {"idea-0001": "Best bounded candidate"},
            }
        ),
        encoding="utf-8",
    )
    assert advance_cycle(workspace, "wheel-topic").state == "awaiting_human_decision"
    code, approval = run_cli(
        [
            "approve-idea",
            "--project",
            "wheel-topic",
            "--idea",
            "idea-0001",
            "--reason",
            "Installed-wheel human gate",
            "--workspace",
            str(workspace),
        ]
    )
    assert code == 0, approval
    assert advance_cycle(workspace, "wheel-topic").state == "completed"
    code, guide = run_cli(
        ["guide", "--project", "wheel-topic", "--workspace", str(workspace)]
    )
    assert code == 0 and "$experiment-advisor" in guide, guide
    assert guide.count("## 下一步") == 1
    assert "## 方法学参考" in guide
    code, final_doctor = run_cli(["doctor", "--workspace", str(workspace)])
    assert code == 0, final_doctor


if __name__ == "__main__":
    main_smoke(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    print("installed-wheel smoke passed")
