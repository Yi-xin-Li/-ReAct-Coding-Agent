# 真实问题台账

只记录实际发生的开发与验证问题。测试里主动构造的越界、错误参数或模型中断属于故障实验，不是开发时真的出现了这些缺陷。

## ENV-001：Python 3.12 启动器记录失效

- 日期/阶段：2026-10-18，第一阶段环境搭建。
- 复现：在项目目录执行 `py -3.12 --version`。
- 预期：返回 Python 3.12 版本。实际：`Unable to create process using ...Accio...python.exe --version`。
- 原因：启动器登记的 Python 路径无法启动；未对全局环境进行修复，不把具体失效原因推断为已确认事实。
- 处理：用 uv 把 Python 3.12 安装到项目 `.tools/python`，通过 `.python-version` 固定版本；缓存放在 `.cache/uv`。
- 验证：`uv sync` 已选择 `CPython 3.12.13` 并创建 `.venv`。
- 状态：项目运行路径已绕开该问题；全局启动器状态未修改、未复验。
- 关联提交：尚未创建提交。

## ENV-002：执行工具的沙箱初始化失败

- 日期/阶段：2026-10-18，第一阶段环境搭建。
- 复现：使用默认沙箱启动项目内的 `uv python install 3.12` 或 `uv sync`。
- 实际错误：`helper_unknown_error: setup refresh had errors`，进程创建前失败，共观察到 3 次。
- 原因：执行服务的 sandbox setup refresh 失败，具体底层原因未知；不能归因于项目代码。
- 处理：在工具审批允许后，以提升执行方式运行相同的项目内安装或验证命令，不更改系统安全设置。
- 验证：隔离解释器、依赖安装、42 个离线测试和演示均已通过；后续验证结果见本阶段进度。
- 状态：当前执行环境存在限制，已找到可用运行方式。
- 关联提交：尚未创建提交。

## ENV-003：Codegraph 未初始化

- 日期/阶段：2026-10-18，探索与工程初始化。
- 复现：对本项目调用 `codegraph_explore`，返回 `CodeGraph not initialized`。初次命令发现未得到可用 CLI，后续提升执行方式查到 npm 全局的 `codegraph.ps1`，不能据此声称 CLI 未安装。
- 影响：当前无法使用项目代码图；不会影响 Python 工具循环的实现。
- 处理：先使用针对性的文件读取；现检查已有 CLI 的初始化方式，不另装同名第三方包。
- 验证：已成功初始化并索引 15 个代码文件；随后 `codegraph_explore` 成功返回源码与调用关系。
- 状态：已解决；同一未初始化状态不重复计为新故障。
- 关联提交：尚未创建提交。

## BUILD-001：发布包名与源码包名不同导致安装失败

- 日期/阶段：2026-10-18，第一阶段首次依赖安装。
- 复现：`uv sync`。
- 预期：安装本地项目。实际：Hatchling 报 `Unable to determine which files to ship inside the wheel`。
- 根因：项目发布名是 `mini-coding-agent`，源码包为 `src/mini_agent`；初始配置遗漏显式包路径，构建器按发布名猜测 `mini_coding_agent` 时找不到源码。
- 处理：在 `tool.hatch.build.targets.wheel` 中指定 `packages = ["src/mini_agent"]`。
- 验证：重新执行 `uv sync` 成功，本地包与 28 个依赖安装完成，CLI 已能被测试导入。
- 状态：已解决。
- 关联提交：尚未创建提交。

## TEST-001：测试错误地假设 Windows 写入 LF

- 日期/阶段：2026-10-18，第一阶段首轮离线测试。
- 复现：`uv run --locked pytest -q`；首轮为 37 passed、1 failed、1 skipped。
- 实际：`test_read_range` 期望 `two\n`，实际读取 `two\r\n`。
- 根因：测试通过 `Path.write_text` 创建样例，Windows 默认进行换行转换；工具按二进制读取后解码，保留了文件的真实换行。错误在测试的隐含平台假设。
- 处理：样例改用明确字节内容，并参数化覆盖 LF 与 CRLF；生产读取逻辑保持原始换行。
- 验证：重跑后 LF 与 CRLF 两个场景均通过，整套测试为 40 passed。
- 状态：已解决。
- 关联提交：尚未创建提交。

## TEST-002：Windows 无权限创建符号链接使边界测试跳过

- 日期/阶段：2026-10-18，第一阶段首轮离线测试。
- 复现：越界测试在临时目录调用 `Path.symlink_to`。
- 实际：账户不能创建符号链接，用例跳过，没有得到真实的链接越界保护证据。
- 处理：Windows 下改为在测试临时目录尝试 NTFS 目录联接；不改变系统权限。联接目标同样位于本用例临时目录。
- 验证：NTFS 联接成功创建，越界写入被拒绝，联接指向的目录未生成文件；整套测试为 40 passed，无跳过。
- 状态：已解决。
- 关联提交：尚未创建提交。

## CHECK-001：异步测试调用阻塞进程触发 Ruff

- 日期/阶段：2026-10-18，联接测试修复后的代码检查。
- 复现：`uv run --locked ruff check .`。
- 实际：`ASYNC221 Async functions should not run processes with blocking methods`，定位到联接测试内的 `subprocess.run`。
- 根因：为了适配 Windows 添加了子进程，却遗漏测试函数本身是 async；功能测试通过不能替代代码检查。
- 处理：改为 `asyncio.create_subprocess_exec` 和有超时的 `communicate`。
- 验证：Ruff 检查与格式检查均通过，40 个功能用例重新执行通过。
- 状态：已解决。
- 关联提交：尚未创建提交。

## ENV-004：CLI 通过管道运行时中文乱码

- 日期/阶段：2026-10-18，离线 CLI 实际运行。
- 复现：通过执行工具运行 `uv run --locked mini-agent demo`。
- 实际：四轮调用和生成脚本均成功，但中文提示在工具输出中显示乱码。
- 原因：Windows 管道文本编码与执行工具的解码方式不一致；功能结果本身未受影响。
- 处理：在开发环境脚本中设置 `PYTHONUTF8=1`，统一 Python 子进程文本编码，不更改系统全局编码。
- 验证：重新加载开发脚本后，终端中文提示正常，四轮演示完成，生成脚本输出 `Hello, Ada!`。
- 状态：已解决。
- 关联提交：尚未创建提交。

## CODE-001：成功 HTTP 响应缺字段时适配器抛出裸 TypeError

- 日期/阶段：2026-10-18，第一阶段模型适配边界检查。
- 来源：离线故障注入发现的实现缺陷；没有证据表明 DeepSeek 真实服务返回过该响应。
- 复现：模拟 HTTP 200 响应省略 `choices`，运行 `test_malformed_success_response_is_a_controlled_error[None]`。
- 预期：适配器抛出可展示的 `ModelFailure`。实际：`len(response.choices)` 触发 `TypeError: object of type 'NoneType' has no len()`；该轮测试为 1 failed、5 passed。
- 根因：只检查候选数量，漏了候选字段缺失时 SDK 可能提供 None 的情况。HTTP 成功不等于业务响应完整。
- 处理：候选数量判断前先检查空值，并参数化覆盖字段缺失与空列表。
- 验证：缺字段与空候选列表两种场景均产生受控错误；全量 42 个离线测试通过，Ruff 也通过。
- 状态：已解决。
- 关联提交：尚未创建提交。

## TOOL-001：Git 中文路径转义导致文件清单检查失败

- 日期/阶段：2026-10-18，GitHub 上传准备检查。
- 复现：将默认 `git ls-files --cached --others --exclude-standard` 的逐行结果传给 PowerShell `Get-Item -LiteralPath`。
- 实际：Git 将中文 IDE 文件名显示为带引号和反斜线数字转义的字符串，Get-Item 报路径不存在。
- 根因：把 Git 面向显示的转义文本当成了真实文件名，不是文件丢失。
- 处理：本次检查使用 `git -c core.quotepath=false ls-files ...`，不修改全局或仓库配置。
- 验证：重新检查成功枚举 35 个文件，合计 132491 字节（加入 IDE 忽略规则之前的快照）。
- 状态：检查方式已修正。
- 关联提交：尚未创建提交。

## TOOL-002：文档命令复验的自动审批超时

- 日期/阶段：2026-10-18，GitHub 发布前整理。
- 操作：准备通过 uv 复验解释器安装、锁定依赖同步和离线演示。
- 实际：自动权限审批未在截止时间内完成，进程未创建；超时不代表判定该操作不安全。
- 处理：改用项目已有 `.venv` 解释器运行同一离线示例，避免重复安装和网络操作。
- 验证：替代验证获准并执行成功，四轮演示完成，生成脚本输出 `Hello, Ada!`；本轮没有声称全新安装复验成功。
- 状态：离线演示验证已完成，安装步骤未重新执行。
- 关联提交：尚未创建提交。

## 后续记录模板

编号；日期/阶段；复现命令；预期与实际；脱敏证据；影响；根因或待验证假设；解决方式；验证结果；状态；关联提交。
