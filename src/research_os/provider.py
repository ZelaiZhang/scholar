from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MissingAPIKey(RuntimeError):
    """Raised when the configured API-key environment variable is unset."""


class ProviderRequestError(RuntimeError):
    """Raised when an external provider request fails."""


class InvalidProviderResponse(RuntimeError):
    """Raised when a provider does not return OpenAI-compatible content."""


Transport = Callable[[str, dict[str, str], dict[str, object], float], dict[str, object]]
MAX_PROVIDER_RESPONSE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CompletionResult:
    content: str
    provenance: dict[str, object]


def _prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            response_bytes = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
            if len(response_bytes) > MAX_PROVIDER_RESPONSE_BYTES:
                raise InvalidProviderResponse("模型服务响应超过 1 MiB 安全上限")
            raw = response_bytes.decode("utf-8", errors="strict")
    except HTTPError as exc:
        raise ProviderRequestError(
            f"模型服务返回 HTTP {exc.code}，请检查地址、模型名和账户状态"
        ) from exc
    except URLError as exc:
        raise ProviderRequestError(f"无法连接模型服务: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderRequestError(f"模型服务在 {timeout:g} 秒内未响应") from exc
    except UnicodeDecodeError as exc:
        raise InvalidProviderResponse("模型服务响应必须是 UTF-8") from exc

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidProviderResponse("模型服务返回的内容不是合法 JSON") from exc
    if not isinstance(decoded, dict):
        raise InvalidProviderResponse("模型服务返回的顶层结构必须是对象")
    return decoded


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str,
        *,
        temperature: float = 0.1,
        timeout: float = 60.0,
        transport: Transport | None = None,
    ):
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url 必须是 HTTP(S) URL")
        if not model.strip() or not api_key_env.strip():
            raise ValueError("model 和 api_key_env 不能为空")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.timeout = timeout
        self.transport = transport or default_transport

    def complete(
        self,
        system: str,
        user: str,
        *,
        external_api_allowed: bool,
    ) -> CompletionResult:
        if not external_api_allowed:
            raise PermissionError("该材料未授权发送到外部 API")
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise MissingAPIKey(f"请设置环境变量 {self.api_key_env}")

        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "stream": False,
        }
        raw = self.transport(
            f"{self.base_url}/chat/completions",
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            payload,
            self.timeout,
        )
        try:
            choices = raw["choices"]
            first = choices[0]  # type: ignore[index]
            content = first["message"]["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise InvalidProviderResponse(
                "模型响应缺少 choices[0].message.content"
            ) from exc
        if not isinstance(content, str):
            raise InvalidProviderResponse("模型响应 content 必须是字符串")

        provenance: dict[str, object] = {
            "provider_base_url": self.base_url,
            "model": self.model,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "temperature": self.temperature,
            "system_prompt_sha256": _prompt_hash(system),
            "user_prompt_sha256": _prompt_hash(user),
            "usage": raw.get("usage", {}),
        }
        if isinstance(raw.get("model"), str):
            provenance["reported_model"] = raw["model"]
        return CompletionResult(content=content, provenance=provenance)
