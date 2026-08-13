from pathlib import Path
import re

import yaml

from research_os.manuscript_markup import parse_annotation


ROOT = Path(__file__).parents[1]
NAMES = (
    "research-project-init",
    "paper-intake",
    "paper-deep-read",
    "literature-synthesis",
    "idea-review",
    "experiment-advisor",
    "result-interpreter",
    "manuscript-assistant",
    "mock-reviewer",
    "research-weekly-review",
    "research-cycle",
)


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    assert text.startswith("---\n")
    _, raw, body = text.split("---", 2)
    return yaml.safe_load(raw), body


def test_all_skills_have_valid_minimal_frontmatter_and_ui_metadata() -> None:
    for name in NAMES:
        skill = ROOT / ".agents" / "skills" / name / "SKILL.md"
        frontmatter, body = split_frontmatter(skill.read_text(encoding="utf-8"))

        assert set(frontmatter) == {"name", "description"}
        assert frontmatter["name"] == name
        assert len(str(frontmatter["description"])) >= 40
        assert "TODO" not in body

        ui = yaml.safe_load(
            (skill.parent / "agents/openai.yaml").read_text(encoding="utf-8")
        )
        assert f"${name}" in ui["interface"]["default_prompt"]


def test_each_skill_has_evidence_and_privacy_guardrails() -> None:
    for name in NAMES:
        text = (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")

        assert "可识别健康信息" in text
        assert "禁止编造" in text
        assert "人工" in text


def test_execution_and_writing_skills_have_specific_hard_gates() -> None:
    experiment = (
        ROOT / ".agents/skills/experiment-advisor/SKILL.md"
    ).read_text(encoding="utf-8")
    manuscript = (
        ROOT / ".agents/skills/manuscript-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "不得运行训练" in experiment
    assert "未核验事实" in manuscript


def test_manuscript_assistant_requires_hidden_provenance_and_final_audit() -> None:
    manuscript = (
        ROOT / ".agents/skills/manuscript-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "每个起草的正文块前" in manuscript
    annotations = re.findall(r"^<!-- research-os:.* -->$", manuscript, re.MULTILINE)
    assert len(annotations) == 6
    assert all(
        parse_annotation(annotation, line=index) is not None
        for index, annotation in enumerate(annotations, 1)
    )
    assert "可见伪标签" in manuscript
    assert (
        ".\\.venv\\Scripts\\research-os.exe manuscript-plan --project <slug> "
        "--as-of YYYY-MM-DD --format markdown"
    ) in manuscript
    assert (
        ".\\.venv\\Scripts\\research-os.exe validate-ledger "
        "projects/<slug>/02-evidence-ledger.yaml --workspace ."
    ) in manuscript
    assert (
        ".\\.venv\\Scripts\\research-os.exe manuscript-audit --project <slug> "
        "--draft projects/<slug>/writing/<draft>.md --as-of YYYY-MM-DD "
        "--format markdown"
    ) in manuscript
    assert "语义蕴含" in manuscript
    assert "退出码 `0`" in manuscript
    assert "退出码 `1`" in manuscript
    assert "退出码 `2`" in manuscript
    assert "可识别健康信息" in manuscript
    assert "绝不覆盖人工文字" in manuscript
    assert "禁止编造引用、结果、伦理审批、数据许可或临床结论" in manuscript
    assert "不得运行训练" in manuscript
    assert "不得运行实验" in manuscript
    assert "不提供个人诊疗建议" in manuscript
    assert "active cycle" in manuscript and "completed" in manuscript
    assert "name+sha256" in manuscript
    assert "Windows ADS" in manuscript


def test_stage_skills_write_completion_markers_only_after_quality_gates() -> None:
    expected = {
        "research-project-init": "brief-complete",
        "literature-synthesis": "synthesis-complete",
        "idea-review": "idea-complete",
        "experiment-advisor": "design-complete",
        "result-interpreter": "result-complete",
    }
    for skill_name, marker in expected.items():
        text = (
            ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
        ).read_text(encoding="utf-8")

        assert f"research-os:stage={marker}" in text
        assert "质量门禁" in text


def test_result_interpreter_binds_completion_to_every_validated_manifest_digest() -> None:
    text = (
        ROOT / ".agents/skills/result-interpreter/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "artifacts/results-manifest.yaml" in text
    assert "research-os guide --project <slug> --workspace ." in text
    assert (
        "<!-- research-os:result-input name=<清单中的直接文件名>; "
        "sha256=<清单中的 64 位小写哈希> -->"
    ) in text
    assert "每个当前" in text
    assert "移除" in text and "过期" in text
    assert "不得编造" in text and "sha256" in text
    assert text.index("research-os:result-input") < text.index(
        "research-os:stage=result-complete"
    )
    assert "顶层独立行" in text
    assert "围栏代码块" in text
    assert "缩进代码块" in text
    assert "普通 HTML 注释" in text
    assert "所有绑定之后" in text


def test_research_cycle_skill_enforces_controller_and_human_boundaries() -> None:
    text = (
        ROOT / ".agents/skills/research-cycle/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "只处理当前阶段" in text
    assert "$paper-intake" in text
    assert "candidates.yaml" in text
    assert "不得用模型调用替代文献检索" in text
    assert "不得运行训练" in text
    assert "selected" in text
    assert "research-os cycle" in text
    assert "selected + 非 completed" in text
    assert "拒绝继续且不写入" in text
