# -*- coding: utf-8 -*-
"""VirtualShellBackend 改造的临时验证脚本（手动运行，无 pytest 依赖）。

运行：cd python && ..\\.venv\\Scripts\\python ..\\tests\\tmp_test_virtual_shell.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

from agent.virtual_shell import VirtualShellBackend  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runtime"))
b = VirtualShellBackend(root_dir=ROOT, inherit_env=True)

FAILED = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    if not cond:
        FAILED.append(name)
    print(f"[{mark}] {name}" + (f"  | {detail}" if detail else ""))


# ---------- 管线1：虚拟路径重写（纯字符串级） ----------
w = b._rewrite_virtual_paths
check("vpath/skills 多段重写", "runtime\\skills\\netease-mail" in w("python /skills/netease-mail/scripts/a.py").replace("/", "\\"))
check("vpath/新建目录多段无条件重写", "runtime\\report\\a.txt" in w("echo hi > /report/a.txt").replace("/", "\\"))
check("vpath/开关不误伤", w("cmd /c dir /b") == "cmd /c dir /b")
check("vpath/盘符不触碰", w("ls D:/skills/x") == "ls D:/skills/x")
check("vpath/URL不触碰", w("curl https://example.com/skills/foo") == "curl https://example.com/skills/foo")
check("vpath/相对路径不触碰", w("python ./local.py") == "python ./local.py")

# ---------- 管线2：命令位置加固（纯字符串级） ----------
h = lambda c: b._harden_command_positions(c)
new, err = h("python --version")
check("harden/python 钉死 venv", err is None and "_find_python" not in new and '"' in new or new.startswith(os.sep) or "python.exe" in new.lower(), new)
venv_py = os.path.join(ROOT, "..", ".venv", "Scripts", "python.exe")
check("harden/python 指向 .venv", ".venv" in new.lower().replace("\\", "/"), new)
new, err = h("pip install foo")
check("harden/pip 展开 -m pip", err is None and "-m pip" in new, new)
new, err = h("echo a & python x.py")
check("harden/分隔符后 python 也钉死", err is None and ".venv" in new.lower(), new)
_, err = h("cmd dir")
check("harden/cmd 缺 /c 被拒绝", err is not None and "/c" in err)
_, err = h("cmd /k dir")
check("harden/cmd /k 被拒绝", err is not None and "/k" in err)
new, err = h('cmd /c start "C:\\My Dir\\a.txt"')
check("harden/start 带引号路径补空标题", err is None and 'start "" "C:\\My Dir' in new, new)
new, err = h("cmd /c start /min notepad")
check("harden/start 程序名不补标题", err is None and new == "cmd /c start /min notepad", new)
new, err = h('python -c "print(1)"')
check("harden/引号内 python 不误替换", err is None and new.count(".venv" if ".venv" in new.lower() else "venv") >= 0 and '"print(1)"' in new, new)

# ---------- 端到端：真实执行 ----------
r = b.execute("python -c \"import sys; print(sys.executable)\"")
check("e2e/python 用 .venv 解释器", ".venv" in r.output.lower().replace("\\", "/"), r.output.strip()[:120])
check("e2e/退出码 0", r.exit_code == 0)

r = b.execute("dir")
check("e2e/dir(GBK) 无乱码", "runtime" in r.output.lower() or "技能" in r.output or "skills" in r.output.lower(), r.output[:80])
check("e2e/dir 不含替换字符", "\ufffd" not in r.output)

r = b.execute("echo hello | findstr ell")
check("e2e/管道可用", r.exit_code == 0 and "hello" in r.output, r.output[:80])

r = b.execute("echo test > /tmp_vshell_check.txt && type /tmp_vshell_check.txt")
check("e2e/重定向+虚拟路径+新建", "test" in r.output, r.output[:120])
_p = os.path.join(ROOT, "tmp_vshell_check.txt")
if os.path.exists(_p):
    os.remove(_p)

r = b.execute("cmd dir")
check("e2e/cmd 假成功拦截", r.exit_code == 1 and "命令未执行" in r.output, r.output[:80])

r = b.execute("python /skills/html-ppt/scripts/new-deck.sh")  # 不存在脚本，验证路径已重写（错误信息含 runtime 路径）
check("e2e/skills 路径重写生效", "runtime" in r.output.lower(), r.output[:160])

r = b.execute("exit 3")
check("e2e/非零退出码透传", r.exit_code != 0, f"exit={r.exit_code}")

print()
print(f"共 {len(FAILED)} 个失败" if FAILED else "全部通过")
sys.exit(1 if FAILED else 0)
