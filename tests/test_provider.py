import json
import research_os.provider as provider_module

import pytest

from research_os.provider import (
    InvalidProviderResponse,
    MissingAPIKey,
    OpenAICompatibleProvider,
)


def test_provider_requires_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = OpenAICompatibleProvider(
        "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY"
    )

    with pytest.raises(MissingAPIKey, match="DEEPSEEK_API_KEY"):
        provider.complete("system", "user", external_api_allowed=True)


def test_provider_blocks_disallowed_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    provider = OpenAICompatibleProvider(
        "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY"
    )

    with pytest.raises(PermissionError, match="未授权"):
        provider.complete("system", "user", external_api_allowed=False)


def test_provider_returns_content_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    def transport(url, headers, payload, timeout):
        assert url == "https://api.deepseek.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer secret"
        assert headers["Content-Type"] == "application/json"
        assert payload["messages"][1]["content"] == "user"
        assert timeout == 60.0
        return {
            "choices": [{"message": {"content": '{"answer":"ok"}'}}],
            "usage": {"total_tokens": 9},
        }

    provider = OpenAICompatibleProvider(
        "https://api.deepseek.com/v1",
        "deepseek-chat",
        "DEEPSEEK_API_KEY",
        transport=transport,
    )

    result = provider.complete("system", "user", external_api_allowed=True)

    assert json.loads(result.content) == {"answer": "ok"}
    assert result.provenance["model"] == "deepseek-chat"
    assert result.provenance["usage"]["total_tokens"] == 9
    assert "created_at" in result.provenance
    assert "secret" not in json.dumps(result.provenance)


def test_provider_rejects_malformed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    provider = OpenAICompatibleProvider(
        "https://example.test/v1",
        "test-model",
        "DEEPSEEK_API_KEY",
        transport=lambda *_: {"choices": []},
    )

    with pytest.raises(InvalidProviderResponse):
        provider.complete("system", "user", external_api_allowed=True)


def test_default_transport_caps_http_response_before_full_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OversizedResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit: int) -> bytes:
            assert limit == provider_module.MAX_PROVIDER_RESPONSE_BYTES + 1
            return b"x" * limit

    monkeypatch.setattr(
        provider_module, "urlopen", lambda *_args, **_kwargs: OversizedResponse()
    )

    with pytest.raises(InvalidProviderResponse, match="1 MiB"):
        provider_module.default_transport(
            "https://provider.test/chat/completions", {}, {}, 1.0
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_url", "http://remote.test/v1"),
        ("base_url", "https://user:password@remote.test/v1"),
        ("base_url", "https://remote.test:invalid/v1"),
        ("base_url", "https://remote.test:70000/v1"),
        ("base_url", "https://remote.test/v1?key=secret"),
        ("base_url", "https://remote.test/v1#fragment"),
        ("model", ""),
        ("model", "model\nname"),
        ("api_key_env", "secret-key"),
        ("temperature", float("nan")),
        ("temperature", float("inf")),
        ("temperature", True),
        ("temperature", -1),
        ("timeout", 0),
        ("timeout", float("nan")),
    ],
)
def test_direct_provider_uses_same_validation_as_role_config(field, value):
    settings = {
        "base_url": "https://provider.test/v1",
        "model": "model",
        "api_key_env": "TEST_KEY",
        "temperature": 0.1,
        "timeout": 60,
        field: value,
    }
    with pytest.raises(ValueError, match=field):
        OpenAICompatibleProvider(**settings)


@pytest.mark.parametrize("url", ["http://localhost:8000/v1", "http://[::1]:8000/v1"])
def test_provider_supports_local_http_for_offline_services(url):
    assert OpenAICompatibleProvider(url, "model", "TEST_KEY").base_url == url
