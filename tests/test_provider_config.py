from pathlib import Path

import pytest
import yaml

from research_os.provider import OpenAICompatibleProvider
from research_os.provider_config import load_provider, load_provider_config


def _write_config(path: Path, role: dict[str, object] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "roles": {
            "economy": role
            or {
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
                "api_key_env": "DEEPSEEK_API_KEY",
                "temperature": 0.1,
                "timeout": 60,
            }
        },
    }
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def test_provider_config_builds_named_openai_compatible_role(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config" / "providers.yaml"
    _write_config(path)

    config = load_provider_config(path)
    provider = load_provider(path, "economy")

    assert config.roles["economy"].model == "deepseek-chat"
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://api.deepseek.com/v1"
    assert provider.api_key_env == "DEEPSEEK_API_KEY"


def test_provider_config_fails_for_missing_file_and_unknown_role(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config" / "providers.yaml"
    with pytest.raises(ValueError, match="providers.yaml"):
        load_provider_config(path)

    _write_config(path)
    with pytest.raises(ValueError, match="unknown provider role"):
        load_provider(path, "expensive")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("base_url", "file:///tmp/model", "base_url"),
        ("base_url", "http://example.com/v1", "HTTPS"),
        ("model", "", "model"),
        ("api_key_env", "secret-key", "api_key_env"),
        ("temperature", 3, "temperature"),
        ("timeout", 0, "timeout"),
    ],
)
def test_provider_config_rejects_unsafe_values(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    path = tmp_path / "providers.yaml"
    role: dict[str, object] = {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "temperature": 0.1,
        "timeout": 60,
    }
    role[field] = value
    _write_config(path, role)

    with pytest.raises(ValueError, match=message):
        load_provider_config(path)


def test_provider_config_rejects_extra_fields_and_invalid_role_names(
    tmp_path: Path,
) -> None:
    path = tmp_path / "providers.yaml"
    _write_config(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["roles"]["economy"]["api_key"] = "must-never-be-stored"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="fields"):
        load_provider_config(path)

    _write_config(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["roles"]["../escape"] = payload["roles"].pop("economy")
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="role"):
        load_provider_config(path)
