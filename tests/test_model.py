import json

import httpx
import pytest
from openai import AsyncOpenAI

from mini_agent.config import Settings
from mini_agent.model import DeepSeekModel
from mini_agent.tools import default_registry
from mini_agent.types import Message, ModelFailure, ModelRequest


def request():
    return ModelRequest(
        messages=(Message(role="user", content="创建脚本"),), tools=default_registry().schemas()
    )


async def test_sdk_request_and_tool_response_are_normalized_offline():
    requests = []

    def handler(received):
        requests.append(json.loads(received.content))
        return httpx.Response(
            200,
            json={
                "id": "test-response",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_sdk",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":"x.py"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
            },
        )

    client = AsyncOpenAI(
        api_key="offline-not-a-real-key",
        base_url="https://offline.invalid",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    model = DeepSeekModel(Settings(), client=client)
    try:
        events = [event async for event in model.stream(request())]
    finally:
        await model.aclose()
    assert len(requests) == 1
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert requests[0]["stream"] is False
    assert requests[0]["tools"][0]["function"]["name"] == "read_file"
    assert events[0].turn.message.tool_calls[0].id == "call_sdk"
    assert events[0].turn.usage.input_tokens == 123


async def test_authentication_error_does_not_leak_provider_body():
    client = AsyncOpenAI(
        api_key="offline-not-a-real-key",
        base_url="https://offline.invalid",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda received: httpx.Response(
                    401,
                    json={
                        "error": {"message": "sensitive-provider-details"},
                    },
                ),
            )
        ),
    )
    model = DeepSeekModel(Settings(), client=client)
    try:
        with pytest.raises(ModelFailure, match="认证失败") as exc:
            _ = [event async for event in model.stream(request())]
        assert "sensitive-provider-details" not in str(exc.value)
    finally:
        await model.aclose()


def test_missing_key_has_clear_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="本地设置"):
        DeepSeekModel(Settings.from_env())


def test_secret_is_not_in_settings_repr():
    assert "private-value" not in repr(Settings(api_key="private-value"))


@pytest.mark.parametrize("choices", [None, []])
async def test_malformed_success_response_is_a_controlled_error(choices):
    payload = {"id": "bad-response", "object": "chat.completion", "created": 1, "model": "test"}
    if choices is not None:
        payload["choices"] = choices
    client = AsyncOpenAI(
        api_key="offline-not-a-real-key",
        base_url="https://offline.invalid",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda received: httpx.Response(200, json=payload),
            )
        ),
    )
    model = DeepSeekModel(Settings(), client=client)
    try:
        with pytest.raises(ModelFailure, match="候选"):
            _ = [event async for event in model.stream(request())]
    finally:
        await model.aclose()
