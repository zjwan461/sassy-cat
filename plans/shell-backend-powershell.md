# Shell 后端改造：真实路径 + 平台原生 shell

> 替代 `python/agent/virtual_shell.py`（已删除）。相关实现：
> [`python/agent/shell_backend.py`](../python/agent/shell_backend.py)。

## 为什么要换

旧方案让 deepagents 的 `LocalShellBackend` 做两件互相打架的事：

1. 文件工具用**虚拟路径**（`/skills/x` → `runtime/skills/x`）；
2. shell 用 `cmd.exe /c` 执行，再靠正则把虚拟路径**猜**回真实路径。

为了兜住 `cmd /c`、`/k`、`start` 标题、盘符、URL、重定向、命令分隔符、GBK 乱码……
在 `virtual_shell.py` 里堆了近 300 行字符串级加固，在 `builtin_tools.py` 里还另有一套
argv 版路径转换。规则越多越容易误伤，模型也很难记住「哪些工具用虚拟路径、哪些用真实路径」。

## 新契约

**只有一套路径：工作区真实路径。**

- 工作区根目录 = `runtime/`（`WORK_DIR`）。相对路径基于它解析，绝对路径按原样使用。
- 文件工具（`ls` / `read_file` / `write_file` / `edit_file` / `glob` / `grep`）与 shell
  共用同一套路径，不再有 `/skills` 这类虚拟挂载。
- 技能目录 = `runtime/skills`（`SKILLS_DIR`），`create_skill` 写入同一目录。

**shell 用平台原生方言。**

| 平台 | 执行方式 |
| --- | --- |
| Windows | `pwsh`（PowerShell 7+，存在时优先）或系统自带 `powershell.exe`（5.1），`-File <临时 .ps1>` |
| macOS / Linux | `/bin/sh -lc <command>` |

Windows 走临时 `.ps1` 而不是 `-Command` 的原因：

- PowerShell 5.1 在 `-Command` 报错时会把整段命令行回显到 stderr（包括我们注入的编码设置）；
- `-File` 不受 Windows 命令行长度限制，引号/换行也不需要二次转义；
- 脚本以 UTF-8 with BOM 写入，5.1 才能正确读取中文命令。

## 行为细节

- **编码**：脚本开头强制 `[Console]::OutputEncoding` / `$OutputEncoding` 为 UTF-8；
  Python 子进程额外注入 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。
- **解释器**：项目 `.venv`（或 `python_env`）的可执行目录被放到 `PATH` 最前，
  命令里的 `python` / `pip` 自然指向项目环境 —— 不再靠正则替换。
- **退出码**：Windows 下脚本末尾执行 `if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }`，
  原生程序（python / git / ffmpeg…）的非零退出能透传；输出末尾附 `[exit code: N]`。
- **超时**：默认 120s，可用 `timeout` 参数覆盖；超时后按进程树清理
  （Windows `taskkill /F /T`，POSIX `killpg`），返回 `[timed out after Ns]` + 已产出的部分输出。
- **输出**：stdout 原样，stderr 以 `[stderr]` 分段；超过 `max_output_bytes` 截断并标注。
- **临时文件**：每次调用一个临时 `.ps1`，执行后删除；错误信息里的临时路径会替换成 `command.ps1`。

## 配套改动

- `engine.py`：`skills=[SKILLS_DIR]`，`backend=create_shell_backend(WORK_DIR)`；
- `prompts.py`：第 6 条重写为「真实路径 + 平台原生 shell」，删掉虚拟/真实两套文件系统的说明；
- `middlewares.py`：技能清单入口路径改为 `skills/<name>/SKILL.md`；
- `create_skill`：`copies.src` 支持相对路径 / 真实绝对路径，同时兼容旧的 `/code/x` 写法；
- `tests/tmp_test_shell_backend.py`：覆盖 cwd、中文编码、退出码、stderr、超时、venv 解释器、
  管道、相对路径写入、文件工具与 shell 同一路径。

## 已知限制

- Windows PowerShell 5.1 不支持 `&&`，提示词已要求用 `;` 串联；装了 PowerShell 7 会自动优先 `pwsh`。
- 每次调用都是新进程，`cd` / 变量不跨命令保留；需要换目录请在单条命令内完成。
- 真实路径模式下文件工具可以访问工作区外的绝对路径（shell 本来就不受限），
  写/改/删仍受 HITL 的 `interruptOn` 约束。
