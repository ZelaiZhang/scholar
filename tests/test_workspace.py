from pathlib import Path

import yaml
from research_os.provider_config import load_provider_config


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


def test_daily_driver_is_documented_and_packaged() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "research-os.exe doctor" in readme
    assert "research-os.exe guide" in readme
    assert "research-os.exe add-sources" in readme
    assert "research-os.exe cycle" in readme
    assert "research-os.exe approve-idea" in readme
    assert "research-os.exe dashboard" in readme
    assert "research-os.exe meeting-brief" in readme
    assert "research-os.exe manuscript-plan" in readme
    assert "research-os.exe kb gaps" in readme
    assert "课题研究驾驶舱" in readme
    assert "--as-of 2026-08-12" in readme
    assert "诊断准确性" in readme
    assert "$research-cycle" in readme
    from research_os import __version__

    assert f'version = "{__version__}"' in pyproject


def test_package_version_matches_project_metadata() -> None:
    from research_os import __version__

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert f'version = "{__version__}"' in pyproject


def test_supervised_cycle_boundaries_and_deepseek_are_documented() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "默认不联网" in readme
    assert "调用前计费" in readme
    assert "不保存隐藏思维链" in readme
    assert "只有研究者" in readme and "selected" in readme
    assert "config/providers.yaml" in readme
    assert "deepseek-v4-flash" in readme
    assert "独立实验仓库" in readme


def test_cycle_recovery_safety_is_documented() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "provider-budget lock" in readme
    assert "create-only commit" in readme
    assert "context-<sha256前16位>.md" in readme
    assert "approve-idea` 会原子完成 run" in readme


def test_provider_example_is_accepted_by_the_real_parser() -> None:
    config = load_provider_config(ROOT / "config/providers.example.yaml")

    assert config.roles["economy"].model == "deepseek-v4-flash"
    assert config.roles["quality"].model == "deepseek-v4-pro"
