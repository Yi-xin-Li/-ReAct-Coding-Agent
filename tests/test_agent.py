import json

import pytest

from mini_agent.agent import Agent
from mini_agent.demo import DEMO_TASK, DemoModel, prepare_demo
from mini_agent.tools import Workspace, default_registry
from mini_agent.types import Message, ModelEvent, ModelFailure, ModelTurn
from tests.helpers import ScriptedModel, final_turn, tool_turn


def make_agent(tmp_path, model, **kwargs):
    return Agent(model, default_registry(), Workspace(tmp_path), **kwargs)


async def collect(agent, task="创建文件"):
    return [event async for event in agent.run(task)]


async def test_model_receives_real_tool_observations(tmp_path):
    model = ScriptedModel(
        [
            tool_turn("write_file", {"path": "new.py", "content": "print('ok')\n"}),
            tool_turn("read_file", {"path": "new.py"}, call_id="call_2"),
            final_turn(),
        ]
    )
    agent = make_agent(tmp_path, model)
    events = await collect(agent)
    assert events[-1].data["reason"] == "completed"
    assert len(model.requests) == 3
    observation = model.requests[1].messages[-1]
    assert observation.role == "tool"
    assert observation.tool_call_id == "call_1"
    assert json.loads(observation.content)["ok"]
    assert json.loads(model.requests[2].messages[-1].content)["data"]["content"] == "print('ok')\n"


async def test_error_is_returned_and_model_can_adjust(tmp_path):
    model = ScriptedModel(
        [
            tool_turn("read_file", {"path": "missing.py"}),
            tool_turn("write_file", {"path": "created.py", "content": "pass"}, call_id="call_2"),
            final_turn(),
        ]
    )
    events = await collect(make_agent(tmp_path, model))
    error = json.loads(model.requests[1].messages[-1].content)["error"]
    assert error["code"] == "file_not_found"
    assert (tmp_path / "created.py").read_text() == "pass"
    assert events[-1].data["reason"] == "completed"


async def test_multiple_tools_keep_order_and_call_ids(tmp_path):
    write = tool_turn("write_file", {"path": "ordered.py", "content": "x = 1"})
    read = tool_turn("read_file", {"path": "ordered.py"}, call_id="call_2")
    turn = ModelTurn(
        message=Message(
            role="assistant",
            tool_calls=write.message.tool_calls + read.message.tool_calls,
        ),
        finish_reason="tool_calls",
    )
    model = ScriptedModel([turn, final_turn()])
    await collect(make_agent(tmp_path, model))
    observations = [message for message in model.requests[1].messages if message.role == "tool"]
    assert [message.tool_call_id for message in observations] == ["call_1", "call_2"]
    assert json.loads(observations[1].content)["data"]["content"] == "x = 1"


@pytest.mark.parametrize("reason", ["length", "content_filter", "stop"])
async def test_incomplete_or_mismatched_response_never_writes(tmp_path, reason):
    candidate = tool_turn("write_file", {"path": "bad.py", "content": "x"})
    candidate = candidate.model_copy(update={"finish_reason": reason})
    model = ScriptedModel([candidate])
    events = await collect(make_agent(tmp_path, model))
    assert events[-1].data["reason"] == "incomplete_turn"
    assert not (tmp_path / "bad.py").exists()


async def test_duplicate_ids_never_execute(tmp_path):
    first = tool_turn("write_file", {"path": "bad.py", "content": "x"})
    bad = ModelTurn(
        message=Message(
            role="assistant",
            tool_calls=first.message.tool_calls * 2,
        ),
        finish_reason="tool_calls",
    )
    events = await collect(make_agent(tmp_path, ScriptedModel([bad])))
    assert events[-1].data["reason"] == "incomplete_turn"
    assert not (tmp_path / "bad.py").exists()


async def test_step_limit_ends_with_complete_tool_messages(tmp_path):
    model = ScriptedModel([tool_turn("read_file", {"path": "missing.py"})])
    agent = make_agent(tmp_path, model, max_steps=1)
    events = await collect(agent)
    assert events[-1].data["reason"] == "step_limit"
    assert agent.messages[-1].role == "tool"


async def test_context_limit_prevents_request(tmp_path):
    model = ScriptedModel([])
    events = await collect(make_agent(tmp_path, model, max_input_bytes=1))
    assert events[-1].data["reason"] == "context_limit"
    assert not model.requests


async def test_repeated_errors_skip_remaining_actions_but_keep_protocol_complete(tmp_path):
    bad = tuple(
        tool_turn("read_file", {"path": "missing.py"}, call_id=str(i)).message.tool_calls[0]
        for i in range(3)
    )
    write = tool_turn("write_file", {"path": "skipped.py", "content": "x"}, call_id="write")
    turn = ModelTurn(
        message=Message(
            role="assistant",
            tool_calls=bad + write.message.tool_calls,
        ),
        finish_reason="tool_calls",
    )
    agent = make_agent(tmp_path, ScriptedModel([turn]))
    events = await collect(agent)
    assert events[-1].data["reason"] == "repeated_tool_error"
    assert not (tmp_path / "skipped.py").exists()
    assert json.loads(agent.messages[-1].content)["error"]["code"] == "skipped"
    assert len([message for message in agent.messages if message.role == "tool"]) == 4


async def test_failure_after_completed_event_does_not_execute_tools(tmp_path):
    class BrokenModel:
        async def stream(self, request):
            turn = tool_turn("write_file", {"path": "bad.py", "content": "x"})
            yield ModelEvent(kind="turn", turn=turn)
            raise ModelFailure("模拟响应中断")

    events = await collect(make_agent(tmp_path, BrokenModel()))
    assert events[-1].data["reason"] == "model_error"
    assert not (tmp_path / "bad.py").exists()


async def test_in_memory_conversation_keeps_previous_task(tmp_path):
    model = ScriptedModel([final_turn("第一轮"), final_turn("第二轮")])
    agent = make_agent(tmp_path, model)
    await collect(agent, "任务一")
    await collect(agent, "任务二")
    users = [message.content for message in model.requests[1].messages if message.role == "user"]
    assert users == ["任务一", "任务二"]


async def test_demo_creates_and_reads_back_real_file(tmp_path):
    workspace = prepare_demo(tmp_path / "中文 演示")
    agent = Agent(DemoModel(), default_registry(), workspace)
    events = await collect(agent, DEMO_TASK)
    assert events[-1].data["reason"] == "completed"
    code = (workspace.root / "hello.py").read_text(encoding="utf-8")
    assert "def greet(name: str)" in code
    observations = [message for message in agent.messages if message.role == "tool"]
    assert json.loads(observations[-1].content)["data"]["content"] == code
