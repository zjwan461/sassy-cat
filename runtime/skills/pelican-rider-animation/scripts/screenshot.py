#!/usr/bin/env python3
"""Headless screenshot check for an animated HTML file (第四关 · 渲染层验证).

为什么需要它：
    smoke_test.py 跑的是桩 DOM，只证明"脚本没报错、坐标算出来了"；
    check_rig_geometry.py 是纯数学，只证明"几何自洽"。
    两者都**看不到真实渲染结果**。一类最常见的失败是：
    画面全空、少了一个图层、鸟少了一条腿 —— 而前面两关全绿。
    唯一能抓到这类问题的手段就是：真浏览器渲染一次，截图，看一眼。

设计原则（重要）：
    **不写死浏览器路径。** 不同机器上 Chrome/Edge 装在哪五花八门，
    hardcode 到 skill 里等于把技能绑死在某台电脑上。这里按以下顺序分层探测：
      1) 环境变量：PELICAN_BROWSER / CHROME_PATH / PUPPETEER_EXECUTABLE_PATH
      2) PATH 里找 chrome / chromium / msedge / google-chrome 等可执行名
      3) 各平台常见安装位置（Windows / macOS / Linux 的若干候选目录）
    全都找不到时 —— **不算失败，优雅跳过**（退出码 0），并打印安装提示。
    这样技能在任何机器上都通用：有浏览器就多一道保障，没有也不阻断交付。

双时间点对比：
    只截一帧无法区分"动画在跑"和"页面卡在第一帧"。脚本默认在
    --virtual-time-budget 的两个取值（如 300ms 与 1800ms）各截一帧，
    若两帧字节完全相同，说明画面没有推进，输出 ❌。

用法：
    python screenshot.py path/to/animation.html
    python screenshot.py path/to/animation.html --outdir /tmp/shots --width 1100 --height 620
    python screenshot.py path/to/animation.html --times 500 2000 4000   # 多时间点
    python screenshot.py path/to/animation.html --browser /path/to/chrome  # 手动指定

退出码：
    0 = 截图成功（或浏览器不可用导致跳过）
    1 = 浏览器存在但截图失败，或双帧完全相同（画面未推进）
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 常见可执行名（PATH 里找）
PATH_NAMES = [
    "chrome", "chrome.exe",
    "google-chrome", "google-chrome-stable",
    "chromium", "chromium-browser", "chromium.exe",
    "msedge", "msedge.exe",
    "brave", "brave-browser",
    "headless-shell", "chrome-headless-shell",
]

# 环境变量（用户/别的工具可能已经指定过）
ENV_KEYS = [
    "PELICAN_BROWSER",
    "CHROME_PATH",
    "CHROMIUM_PATH",
    "PUPPETEER_EXECUTABLE_PATH",
    "BROWSER",
]

WINDOWS_DIRS = [
    r"%PROGRAMFILES%\Google\Chrome\Application",
    r"%PROGRAMFILES(X86)%\Google\Chrome\Application",
    r"%LOCALAPPDATA%\Google\Chrome\Application",
    r"%PROGRAMFILES%\Microsoft\Edge\Application",
    r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application",
    r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application",
    r"%LOCALAPPDATA%\Chromium\Application",
    r"%PROGRAMFILES%\Chromium\Application",
]
WINDOWS_EXES = ["chrome.exe", "msedge.exe", "brave.exe", "chromium.exe"]

MAC_DIRS = [
    "/Applications/Google Chrome.app/Contents/MacOS",
    "/Applications/Chromium.app/Contents/MacOS",
    "/Applications/Microsoft Edge.app/Contents/MacOS",
    "/Applications/Brave Browser.app/Contents/MacOS",
    "~/Applications/Google Chrome.app/Contents/MacOS",
]
MAC_EXES = ["Google Chrome", "Chromium", "Microsoft Edge", "Brave Browser"]

LINUX_DIRS = [
    "/usr/bin", "/usr/local/bin", "/snap/bin", "/opt/google/chrome",
    "/opt/chromium", "/usr/lib/chromium", "/usr/lib/chromium-browser",
    "/var/lib/flatpak/exports/bin",
]
LINUX_EXES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "brave-browser", "chrome",
]


def _expand(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(path))


def find_browser(explicit: str = None):
    """分层探测可执行浏览器。返回绝对路径或 None。"""
    if explicit:
        p = Path(_expand(explicit))
        return str(p) if p.is_file() else None

    for key in ENV_KEYS:
        val = os.environ.get(key)
        if not val:
            continue
        cand = Path(_expand(val))
        if cand.is_file():
            return str(cand)

    for name in PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found

    system = platform.system()
    if system == "Windows":
        dirs, exes = WINDOWS_DIRS, WINDOWS_EXES
    elif system == "Darwin":
        dirs, exes = MAC_DIRS, MAC_EXES
    else:
        dirs, exes = LINUX_DIRS, LINUX_EXES

    for d in dirs:
        base = Path(_expand(d))
        for exe in exes:
            cand = base / exe
            if cand.is_file():
                return str(cand)
    return None


def shoot(exe: str, page_uri: str, out_png: Path, width: int, height: int,
          budget_ms: int, timeout: int) -> tuple:
    """调用一次 headless 截图。返回 (ok, size_or_none, stderr_tail)。"""
    profile = tempfile.mkdtemp(prefix="pelican_shot_")
    cmd = [
        exe,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        f"--virtual-time-budget={budget_ms}",
        f"--user-data-dir={profile}",
        f"--screenshot={out_png}",
        page_uri,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        err = (r.stderr or "").strip()[-400:]
        rc = r.returncode
    except subprocess.TimeoutExpired:
        return False, None, "超时"
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    if out_png.is_file() and out_png.stat().st_size > 0:
        return True, out_png.stat().st_size, err
    return False, None, f"rc={rc} {err}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless screenshot check (render-layer gate)")
    ap.add_argument("html", help="待截图的 HTML 文件路径")
    ap.add_argument("--outdir", default=None, help="截图输出目录（默认与 HTML 同级的 _shots/）")
    ap.add_argument("--width", type=int, default=1100, help="窗口宽（默认 1100）")
    ap.add_argument("--height", type=int, default=620, help="窗口高（默认 620）")
    ap.add_argument("--times", type=int, nargs="+", default=[200, 1300, 5200],
                    help="虚拟时间预算的多个时间点(ms)，用于确认画面在推进"
                         "（默认 200 1300 5200 —— 三点且拉开跨度，避免车轮周期相位撞车）")
    ap.add_argument("--browser", default=None, help="手动指定浏览器可执行文件路径")
    ap.add_argument("--timeout", type=int, default=180, help="单次截图超时秒数")
    args = ap.parse_args()

    page = Path(args.html)
    if not page.is_file():
        sys.exit(f"❌ 文件不存在: {page}")

    exe = find_browser(args.browser)
    if not exe:
        print("ℹ️  未在本机找到可用的 Chrome/Chromium/Edge，跳过渲染层截图检查。")
        print("    这一步是可选的：有浏览器时能多一道'肉眼级'保障，没有也不阻断交付。")
        print("    如想启用，可安装任一基于 Chromium 的浏览器，或通过环境变量指定，例如：")
        print("      Windows : set PELICAN_BROWSER=C:\\path\\to\\chrome.exe")
        print("      macOS   : export PELICAN_BROWSER='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'")
        print("      Linux   : export PELICAN_BROWSER=/usr/bin/google-chrome")
        print("    或用参数直接指定：--browser /path/to/chrome")
        return 0

    print(f"🧭 使用浏览器: {exe}")

    outdir = Path(_expand(args.outdir)) if args.outdir else (page.parent / "_shots")
    outdir.mkdir(parents=True, exist_ok=True)
    uri = page.resolve().as_uri()

    results = []
    for ms in args.times:
        out_png = outdir / f"{page.stem}_t{ms}ms.png"
        ok, size, err = shoot(exe, uri, out_png, args.width, args.height, ms, args.timeout)
        if ok:
            print(f"✅ t={ms}ms  →  {out_png}  ({size / 1024:.1f} KB)")
        else:
            print(f"❌ t={ms}ms  截图失败: {err}")
        results.append((ms, ok, out_png, size))

    failed = [r for r in results if not r[1]]
    if failed:
        print("")
        print(f"❌ {len(failed)}/{len(results)} 个时间点截图失败。")
        return 1

    # 多帧对比：所有时间点截图字节若完全一致，说明画面根本没推进。
    # 注意：不能只比"文件大小"，也不能只用两个时间点——循环动画存在车轮
    # 周期相位，两个恰好相差整数圈的点会撞车（实测 300ms/1800ms 就撞了）。
    # 因此默认取三个拉开跨度的时间点，并比对实际字节。
    if len(results) > 1:
        first = results[0][2].read_bytes()
        same = all(r[2].read_bytes() == first for r in results[1:])
        if same:
            print("")
            print(f"❌ {len(results)} 个时间点截出的图完全一致 —— 画面没有推进"
                  "（动画可能卡在第一帧或整页空白）。")
            print("   请检查：requestAnimationFrame 循环是否真的在改属性、是否被异常打断。")
            print("   若确认动画是循环型且周期极长，可用 --times 拉开更大跨度复测。")
            return 1

    print("")
    print(f"🎉 渲染层检查通过：{len(results)} 个时间点均成功截图，且画面随时间变化。")
    print("   ⚠️ 截图只能证明'渲染出来了'，不能证明'画得像鹈鹕'——请人工看一眼图：")
    print("      要素齐不齐（两个轮子有辐条 / 鸟坐在座垫上 / 长喙 + 喉囊 / 翅尖搭把套）。")
    print(f"   截图目录：{outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())