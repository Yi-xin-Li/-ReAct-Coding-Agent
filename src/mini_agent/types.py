"""模块之间传递的数据；不让 SDK 类型扩散到内核。"""

from collections.abc import AsyncIterator
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolCall(Record):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: str


class Message(Record):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def check_role_fields(self) -> "Message":
        if self.tool_calls and self.role != "assistant":
            raise ValueError("Only assistant messages can contain tool calls")
        if self.role == "tool" and (not self.tool_call_id or self.content is None):
            raise ValueError("Tool messages need an ID and a result")
        if self.role != "tool" and self.tool_call_id is not None:
            raise ValueError("Only tool results can reference a tool call ID")
        if self.role != "assistant" and self.content is None:
            raise ValueError("This message role requires content")
        return self

    def to_wire(self) -> dict:
        message: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in self.tool_calls
            ]
        if self.tool_call_id is not None:
            message["tool_call_id"] = self.tool_call_id
        return message


class ToolError(Record):
    code: str
    message: str


class ToolResult(Record):
    ok: bool
    data: dict[str, JsonValue] = Field(default_factory=dict)
    error: ToolError | None = None
    truncated: bool = False

    @classmethod
    def failure(cls, code: str, message: str) -> "ToolResult":
        return cls(ok=False, error=ToolError(code=code, message=message))


class Usage(Record):
    # None 代表未知，模拟运行不能伪装成真实消耗为零。
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ModelTurn(Record):
    message: Message
    finish_reason: str
    usage: Usage = Field(default_factory=Usage)
    model: str = "unknown"
    response_id: str | None = None


class ModelRequest(Record):
    messages: tuple[Message, ...]
    tools: tuple[dict, ...]


class ModelEvent(Record):
    kind: Literal["text_delta", "turn"]
    text: str = ""
    turn: ModelTurn | None = None


class AgentEvent(Record):
    kind: Literal[
        "model_started", "assistant", "tool_started", "tool_finished", "usage", "error", "done"
    ]
    step: int
    data: dict[str, JsonValue] = Field(default_factory=dict)


class ModelClient(Protocol):
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...


class ModelFailure(Exception):
    """只携带可以展示给用户的信息，不透出 SDK 请求或认证头。"""
