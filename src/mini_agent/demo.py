"""固定脚本化模型，用于观察循环和离线验证，不能证明 LLM 编码能力。"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

from mini_agent.tools import Workspace
from mini_agent.types import Message, ModelEvent, ModelRequest, ModelTurn, ToolCall

DEMO_TASK = "读取 requirements.md，创建符合要求的 hello.py，再读回检查。不要执行命令。"
DEMO_REQUIREMENTS = (
    "创建 hello.py，提供 greet(name) 返回 Hello, {name}!；直接运行时打印 Hello, Ada!。\n"
)
DEMO_CODE = """def greet(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("Ada"))
"""


def prepare_demo(root: Path) -> Workspace:
    root.mkdir(parents=True, exist_ok=True)
    workspace = Workspace(root)
    if workspace.resolve("hello.py").exists():
        raise ValueError("演示的 hello.py 已存在，请选择新的 --workspace；不会覆盖已有文件")
    try:
        with workspace.resolve("requirements.md").open("x", encoding="utf-8") as handle:
            handle.write(DEMO_REQUIREMENTS)
    except FileExistsError as exc:
        raise ValueError("演示的 requirements.md 已存在，请选择新的 --workspace") from exc
    return workspace


class DemoModel:
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        observations = [message for message in request.messages if message.role == "tool"]
        if observations and not json.loads(observations[-1].content)["ok"]:
            message = Message(role="assistant", content="离线演示遇到工具错误，请查看上面的结果。")
            reason = "stop"
        elif len(observations) < 3:
            index = len(observations)
            name, args = [
                ("read_file", {"path": "requirements.md"}),
                ("write_file", {"path": "hello.py", "content": DEMO_CODE}),
                ("read_file", {"path": "hello.py"}),
            ][index]
            message = Message(
                role="assistant",
                tool_calls=(
                    ToolCall(
                        id=f"demo_call_{index + 1}",
                        name=name,
                        arguments=json.dumps(args, ensure_ascii=False),
                    ),
                ),
            )
            reason = "tool_calls"
        else:
            message = Message(
                role="assistant",
                content="离线演示结束：已创建并读回 hello.py；Agent 未运行脚本或测试。",
            )
            reason = "stop"
        yield ModelEvent(
            kind="turn",
            turn=ModelTurn(
                message=message,
                finish_reason=reason,
                model="scripted-offline-demo",
            ),
        )
