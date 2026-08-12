from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_workspace_public_data_boundary_is_explicit() -> None:
    config = yaml.safe_load(
        (ROOT / "config/research.yaml").read_text(encoding="utf-8")
    )

    assert config["privacy"]["allow_identifiable_health_data"] is False
    assert config["privacy"]["external_api_default"] is False
    assert config["evidence"]["require_locator_for_verified_fact"] is True


def test_paper_card_requires_evidence_labels() -> None:
    text = (ROOT / "src/research_os/templates/paper-card.md").read_text(
        encoding="utf-8"
    )

    assert "reported_fact" in text
    assert "model_inference" in text
    assert "researcher_note" in text
    assert "页码/章节" in text


def test_workspace_rules_forbid_fabrication_sensitive_data_and_training() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "禁止编造引用" in text
    assert "可识别健康信息" in text
    assert "不得执行训练" in text
    assert "人工笔记" in text


def test_local_secrets_and_raw_artifacts_are_ignored() -> None:
    patterns = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in patterns
    assert ".venv/" in patterns
    assert "inbox/**/*.pdf" in patterns
    assert "*.provenance.json" not in patterns
