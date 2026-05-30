"""Direct OpenRouter Chat Completions client."""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4.1-mini"


class OpenRouterConfigError(RuntimeError):
    """Raised when OpenRouter configuration is missing or invalid."""


class ChatToolCall(BaseModel):
    """Parsed tool call returned by a chat completion."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatCompletionResult(BaseModel):
    """Parsed OpenRouter chat completion response."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    tool_calls: list[ChatToolCall] = Field(default_factory=list)
    raw: dict[str, Any]


class OpenRouterClient:
    """Minimal non-streaming OpenRouter client with tool and JSON-schema support."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
        )
        if not self.api_key:
            raise OpenRouterConfigError("OPENROUTER_API_KEY is required for --llm mode")
        self.model = (
            model or os.getenv("LANGGRAPH_MAINTENANCE_LLM_MODEL") or DEFAULT_MODEL
        )
        self._client = http_client or httpx.Client(timeout=60)

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> ChatCompletionResult:
        """Call OpenRouter chat completions and parse content/tool calls."""

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "maintenance_agent_output",
                    "strict": True,
                    "schema": response_schema,
                },
            }

        response = self._client.post(
            OPENROUTER_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterConfigError(
                "OpenRouter response did not include a chat message"
            ) from exc

        tool_calls: list[ChatToolCall] = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                import json

                arguments = json.loads(arguments or "{}")
            tool_calls.append(
                ChatToolCall(
                    id=str(call.get("id", "")),
                    name=str(function.get("name", "")),
                    arguments=arguments,
                )
            )
        return ChatCompletionResult(
            content=message.get("content"),
            tool_calls=tool_calls,
            raw=data,
        )
