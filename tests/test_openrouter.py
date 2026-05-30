from __future__ import annotations

import json

import httpx
import pytest

from langgraph_maintenance_agent.llm.openrouter import (
    OPENROUTER_CHAT_COMPLETIONS_URL,
    OpenRouterClient,
    OpenRouterConfigError,
)


def test_missing_openrouter_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(OpenRouterConfigError, match="OPENROUTER_API_KEY"):
        OpenRouterClient()


def test_openrouter_model_name_uses_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LANGGRAPH_MAINTENANCE_LLM_MODEL", "example/model")

    client = OpenRouterClient(
        http_client=httpx.Client(transport=httpx.MockTransport(lambda _: None))
    )

    assert client.model == "example/model"


def test_openrouter_parses_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == OPENROUTER_CHAT_COMPLETIONS_URL
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "git_status",
                                        "arguments": json.dumps({"repo_name": "demo"}),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    client = OpenRouterClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.chat(messages=[{"role": "user", "content": "inspect"}])

    assert result.tool_calls[0].name == "git_status"
    assert result.tool_calls[0].arguments == {"repo_name": "demo"}


def test_openrouter_sends_json_schema_response_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    client = OpenRouterClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.chat(
        messages=[{"role": "user", "content": "inspect"}],
        response_schema={"type": "object"},
    )

    assert result.content == '{"ok": true}'
