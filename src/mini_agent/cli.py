import argparse
import asyncio
from pathlib import Path

from pydantic import ValidationError
from rich.console import Console

from mini_agent.agent import Agent
from mini_agent.config import Settings
from mini_agent.demo import DEMO_TASK, DemoModel, prepare_demo
from mini_agent.model import DeepSeekModel
from mini_agent.tools import Workspace, default_registry
from mini_agent.types import AgentEvent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mini Coding Agent：自己实现的工具调用循环")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="运行脚本化离线演示，不访问模型 API")
    demo.add_argument("--workspace", type=Path, default=Path(".demo/first-run"))
    for command in (demo,):
        command.add_argument("--json-events", action="store_true", help="逐行输出 JSON 事件")
    for name, help_text in (("run", "执行一次真实模型任务"), ("chat", "真实模型多轮对话")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--live", action="store_true", required=True, help="明确启用收费 API")
        command.add_argument("--max-steps", type=int, default=24)
        command.add_argument("--json-events", action="store_true")
        if name == "run":
            command.add_argument("--task", required=True)
    return parser


def display(event: AgentEvent, console: Console, *, json_events: bool) -> None:
    if json_events:
        console.print(event.model_dump_json(), markup=False, highlight=False, soft_wrap=True)
    elif event.kind == "model_started":
        console.print(f"[{event.step}] 请求模型", markup=False)
    elif event.kind == "assistant":
        console.print(str(event.data["text"]), markup=False, highlight=False)
    elif event.kind == "tool_started":
        console.print(f"  工具 → {event.data['name']}", markup=False)
    elif event.kind == "tool_finished":
        result = event.data["result"]
        if result["ok"]:
            console.print("  结果 ← 成功", markup=False)
        else:
            console.print(f"  结果 ← {result['error']['message']}", markup=False)
    elif event.kind == "error":
        console.print(f"错误：{event.data['message']}", markup=False)
    elif event.kind == "done":
        console.print(f"结束：{event.data['reason']}", markup=False)


async def run_task(agent: Agent, task: str, console: Console, *, json_events: bool) -> int:
    reason = "incomplete"
    async for event in agent.run(task):
        display(event, console, json_events=json_events)
        if event.kind == "done":
            reason = event.data["reason"]
    return 0 if reason == "completed" else 1


async def execute(args: argparse.Namespace, console: Console) -> int:
    if args.command == "demo":
        workspace = prepare_demo(args.workspace)
        Console(stderr=True).print(
            "离线演示：固定脚本化模型，不访问 API，不代表真实模型验收。",
            markup=False,
        )
        agent = Agent(DemoModel(), default_registry(), workspace)
        return await run_task(agent, DEMO_TASK, console, json_events=args.json_events)

    settings = Settings.from_env(max_steps=args.max_steps)
    workspace = Workspace(args.workspace)
    model = DeepSeekModel(settings)
    try:
        agent = Agent(
            model,
            default_registry(),
            workspace,
            max_steps=settings.max_steps,
            max_input_bytes=settings.max_input_bytes,
        )
        if args.command == "run":
            return await run_task(agent, args.task, console, json_events=args.json_events)
        console.print("多轮对话：/help 查看帮助，/exit 退出。会话目前仅保存在内存。", markup=False)
        while True:
            try:
                task = await asyncio.to_thread(input, "你 > ")
            except EOFError:
                return 0
            if task.strip() == "/exit":
                return 0
            if task.strip() == "/help":
                console.print(
                    "当前支持 /help、/exit；保存、恢复和压缩将在第三阶段加入。", markup=False
                )
            elif task.strip():
                await run_task(agent, task, console, json_events=args.json_events)
    finally:
        await model.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()
    try:
        return asyncio.run(execute(args, console))
    except KeyboardInterrupt:
        console.print("已中断。", markup=False)
        return 130
    except ValidationError:
        console.print("配置无效，请检查参数范围。", markup=False)
        return 2
    except (ValueError, OSError) as exc:
        console.print(f"启动失败：{exc}", markup=False)
        return 2
