# Mini Coding Agent

用 Python 自己实现工具调用与 ReAct 循环，逐步构建用于学习和实习展示的终端 Coding Agent。完整路线见 [项目计划](PROJECT_PLAN.md)。

**当前版本：第一阶段最小闭环。** 已支持文件读取、创建新文件、工具参数校验、顺序执行、错误反馈、步数/输入上限、事件输出和真实模型多轮对话入口。

尚未实现局部编辑、命令执行、自动测试、搜索代码、压缩、会话持久化和联网工具。第一阶段只创建新文件，拒绝覆盖已有内容。模型接口当前是非流式请求，通过统一事件接口输出完整轮次。

## Windows 快速开始

准备好 uv，将仓库克隆或下载到任意目录，然后在**仓库根目录**打开 PowerShell（该目录包含 `pyproject.toml`）。项目通过 `.python-version` 固定 Python 3.12，无需使用原作者的本机路径。

```powershell
. .\scripts\dev.ps1
uv python install 3.12
uv sync --locked
uv run --locked mini-agent demo
```

开发脚本将解释器和缓存放在项目内，并启用 Python UTF-8 模式；`--locked` 使用已提交的 `uv.lock`，避免安装时静默更新依赖版本。

演示会在 `.demo/first-run` 中创建需求文件和 `hello.py`，运行“读需求 → 写文件 → 读回 → 回复”四轮循环。它使用固定脚本化模型，不请求收费接口，也不证明真实 LLM 能完成编码任务。

重复运行时选一个新目录，避免覆盖你已经生成的文件：

```powershell
uv run --locked mini-agent demo --workspace '.demo/second-run'
uv run --locked mini-agent demo --workspace '.demo/events-run' --json-events
```

生成的脚本可由你手动验证；这条命令不是 Agent 自动执行的：

```powershell
uv run --locked python '.demo/first-run/hello.py'
# 预期：Hello, Ada!
```

## 连接真实模型

在本地进程环境中设置 `DEEPSEEK_API_KEY`，不要将密钥发送到聊天或提交 Git。`.env.example` 仅供查看变量名，当前不会自动加载 `.env`。

可选变量是 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL`。默认使用官方地址、`deepseek-flash` 和关闭 thinking 的原生工具调用；别名是否对当前账号可用仍需实际联调。[官方接口说明](https://api-docs.deepseek.com/api/create-chat-completion/)

```powershell
New-Item -ItemType Directory -Path '.demo/live-workspace' -Force
uv run --locked mini-agent run --live --workspace '.demo/live-workspace' --max-steps 6 --task '创建一个包含 greet(name) 函数的 hello.py，读回检查；不要声称运行过测试。'
uv run --locked mini-agent chat --live --workspace '.demo/live-workspace'
```

只有明确使用 `--live` 的 `run` / `chat` 才可能访问收费模型 API。当前无人民币累计预算账本，先用短任务联调并查看服务商账单；全局预算控制、用量汇总与持久化按第三阶段实现。SDK 隐式重试已关闭。

## 验证与阅读顺序

```powershell
. .\scripts\dev.ps1
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

推荐按 `types.py → tools.py → agent.py → model.py → cli.py` 阅读。详细数据流和练习见 [第一阶段学习笔记](docs/learning-log.md)，真实故障见 [问题台账](docs/problem-log.md)。

```text
src/mini_agent/
  types.py    消息、调用、工具结果、模型事件与 Agent 事件
  config.py   本地配置和密钥类型
  tools.py    文件边界、工具 schema、参数校验与实际执行
  agent.py    模型 → 工具 → 观察 → 再请求模型
  model.py    DeepSeek / SDK 适配
  demo.py     固定脚本化离线模型
  cli.py      终端输入与展示
tests/        默认不访问网络的验证
docs/         学习、问题、设计决策、优化和进度
```

文件路径限制用于保护工作目录，不能代替操作系统沙箱。第一阶段没有命令工具；生成的代码不会自动执行。请先在自己的测试目录学习。
