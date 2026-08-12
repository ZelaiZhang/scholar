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
