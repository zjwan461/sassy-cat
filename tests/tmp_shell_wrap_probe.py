"""shell 包装方式对比探针：确认 Windows 下 cmd 调用该用 argv 还是 shell=True。

背景：Python 在 Windows 上 shell=True 会把命令包成 cmd.exe /c "<命令>"，
当命令本身以 cmd 开头时，cmd 的引号剥离规则会多留一个 " 传给真正的命令。
"""

import os
import subprocess

CASES = [
    ["python", "-c", "print(123)"],
    ["cmd", "/c", "echo", "hello"],
    ["cmd", "/c", "echo", "hello", "world"],
    ["cmd", "/c", "python", "-c", "print(123)"],
    ["cmd", "/c", "dir", "/b", os.path.join(os.getcwd(), "runtime", "skills")],
    ["cmd.exe", "/c", "echo", "hello"],
]


def main():
    print("COMSPEC =", os.environ.get("COMSPEC"))
    for cmd in CASES:
        s = subprocess.list2cmdline(cmd)
        try:
            o1 = subprocess.run(s, shell=True, capture_output=True, timeout=30).stdout
        except Exception as e:  # noqa: BLE001
            o1 = f"<{e}>".encode()
        try:
            o2 = subprocess.run(cmd, shell=False, capture_output=True, timeout=30).stdout
        except Exception as e:  # noqa: BLE001
            o2 = f"<{e}>".encode()
        print(f"\ncmd        : {cmd}")
        print(f"  shell=True : {o1!r}")
        print(f"  argv       : {o2!r}")


if __name__ == "__main__":
    main()