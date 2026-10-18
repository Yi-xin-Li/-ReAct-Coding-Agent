import json
from collections.abc import AsyncIterator

from mini_agent.types import Message, ModelEvent, ModelRequest, ModelTurn, ToolCall


def tool_turn(name: str, arguments: dict | str, *, call_id: str = "call_1") -> ModelTurn:
    return ModelTurn(
        message=Message(
            role="assistant",
            tool_calls=(
                ToolCall(
                    id=call_id,
                    name=name,
                    arguments=json.dumps(arguments) if isinstance(arguments, dict) else arguments,
                ),
            ),
        ),
        finish_reason="tool_calls",
    )


def final_turn(text: str = "完成") -> ModelTurn:
    return ModelTurn(message=Message(role="assistant", content=text), finish_reason="stop")


class ScriptedModel:
    def __init__(self, turns: list[ModelTurn]):
        self.turns = iter(turns)
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        yield ModelEvent(kind="turn", turn=next(self.turns))
