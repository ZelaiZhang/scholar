from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from research_os.provider import OpenAICompatibleProvider, Transport


MAX_CONFIG_BYTES = 1024 * 1024
TOP_LEVEL_KEYS = {"version", "roles"}
ROLE_KEYS = {
    "base_url",
    "model",
    "api_key_env",
    "temperature",
    "timeout",
}
ROLE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ENV_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


@dataclass(frozen=True)
class ProviderRoleConfig:
    base_url: str
    model: str
    api_key_env: str
    temperature: float
    timeout: float


@dataclass(frozen=True)
class ProviderConfig:
    version: int
    roles: dict[str, ProviderRoleConfig]


def _exact_keys(raw: dict[str, object], expected: set[str], *, context: str) -> None:
    if set(raw) != expected:
        raise ValueError(
            f"{context} fields are invalid: missing {sorted(expected - set(raw))}, "
            f"extra {sorted(set(raw) - expected)}"
        )


def _string(raw: object, *, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip() or any(
        ord(character) < 32 for character in raw
    ):
        raise ValueError(f"provider {field} must be a non-empty plain string")
    return raw.strip()


def _number(
    raw: object, *, field: str, minimum: float, maximum: float
) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"provider {field} must be numeric")
    value = float(raw)
    if not minimum <= value <= maximum:
        raise ValueError(
            f"provider {field} must be between {minimum:g} and {maximum:g}"
        )
    return value


def _base_url(raw: object) -> str:
    value = _string(raw, field="base_url").rstrip("/")
    parsed = urlsplit(value)
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("provider base_url is invalid")
    is_local_http = parsed.scheme == "http" and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if parsed.scheme != "https" and not is_local_http:
        raise ValueError("provider base_url must use HTTPS (HTTP is local-only)")
    return value


def _parse_role(raw: object, *, role: str) -> ProviderRoleConfig:
    if not isinstance(raw, dict):
        raise ValueError(f"provider role {role} must be an object")
    _exact_keys(raw, ROLE_KEYS, context=f"provider role {role}")
    api_key_env = _string(raw["api_key_env"], field="api_key_env")
    if not ENV_PATTERN.fullmatch(api_key_env):
        raise ValueError("provider api_key_env must be an uppercase environment name")
    model = _string(raw["model"], field="model")
    if len(model) > 200:
        raise ValueError("provider model is too long")
    return ProviderRoleConfig(
        base_url=_base_url(raw["base_url"]),
        model=model,
        api_key_env=api_key_env,
        temperature=_number(
            raw["temperature"], field="temperature", minimum=0, maximum=2
        ),
        timeout=_number(raw["timeout"], field="timeout", minimum=1, maximum=300),
    )


def load_provider_config(path: Path) -> ProviderConfig:
    try:
        if path.stat().st_size > MAX_CONFIG_BYTES:
            raise ValueError("providers.yaml exceeds the 1 MiB limit")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"providers.yaml cannot be read: {path}") from exc
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"providers.yaml is malformed: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("providers.yaml must be an object")
    _exact_keys(raw, TOP_LEVEL_KEYS, context="providers.yaml")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise ValueError("providers.yaml version must be 1")
    roles_raw = raw["roles"]
    if not isinstance(roles_raw, dict) or not roles_raw:
        raise ValueError("providers.yaml roles must be a non-empty object")
    roles: dict[str, ProviderRoleConfig] = {}
    for raw_name, raw_role in roles_raw.items():
        if not isinstance(raw_name, str) or not ROLE_PATTERN.fullmatch(raw_name):
            raise ValueError(f"invalid provider role name: {raw_name!r}")
        roles[raw_name] = _parse_role(raw_role, role=raw_name)
    return ProviderConfig(version=1, roles=roles)


def load_provider(
    path: Path, role: str, *, transport: Transport | None = None
) -> OpenAICompatibleProvider:
    config = load_provider_config(path)
    selected = config.roles.get(role)
    if selected is None:
        raise ValueError(
            f"unknown provider role {role!r}; available: {', '.join(sorted(config.roles))}"
        )
    return OpenAICompatibleProvider(
        selected.base_url,
        selected.model,
        selected.api_key_env,
        temperature=selected.temperature,
        timeout=selected.timeout,
        transport=transport,
    )
