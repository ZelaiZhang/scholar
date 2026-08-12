from pathlib import Path

import yaml


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
