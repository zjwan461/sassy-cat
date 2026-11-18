"""音色下载 / 校验工具。

新机器、新同事、重新打包之前，跑一次这个脚本就能把 `voices.json` 里声明的
所有权重和参考音频拉到本地，并逐个校验大小与 sha256。

只用标准库（urllib），不依赖 requests，便于在环境还没装好时先跑它。

用法
----
    # 看清单（下载地址、授权、大小）
    python python/tts/fetch_voices.py --list

    # 全量下载（自动跳过已存在且校验通过的文件）
    python python/tts/fetch_voices.py

    # 走代理 + 走镜像站
    python python/tts/fetch_voices.py --proxy http://localhost:11081 \
        --endpoint https://hf-mirror.com

    # 只校验，不下载
    python python/tts/fetch_voices.py --verify

    # 只下某一套
    python python/tts/fetch_voices.py --only tangyuge-v2pp
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

DEFAULT_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
CHUNK = 1 << 20  # 1 MiB


# ---------------------------------------------------------------------------
# 路径解析
# ---------------------------------------------------------------------------


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "voices.json"


def _force_utf8_stdout() -> None:
    """Windows 的 GBK 控制台打印中文/日文路径会抛 UnicodeEncodeError，这里强制 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_vendor_dir(explicit: Optional[str] = None) -> Path:
    """vendor 目录优先级：命令行 > 环境变量 > voices.json > 打包目录 > 同级仓库。"""
    if explicit:
        return Path(explicit)
    env = os.environ.get("GSV_VENDOR_DIR")
    if env:
        return Path(env)
    root = _project_root()
    packaged = root / "vendor" / "gpt-sovits"
    if (packaged / "GPT_SoVITS").is_dir():
        return packaged
    candidates = sorted(root.parent.glob("GPT-SoVITS-v*"))
    for cand in candidates:
        if (cand / "GPT_SoVITS").is_dir():
            return cand
    return packaged


def build_url(endpoint: str, repo: str, remote_path: str) -> str:
    """拼 HF 直链，逐段百分号编码（文件名里有中文/日文/空格/标点）。"""
    seg = "/".join(urllib.parse.quote(p, safe="") for p in remote_path.split("/"))
    return f"{endpoint}/{repo}/resolve/main/{seg}"


# ---------------------------------------------------------------------------
# 校验与下载
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def verify_file(path: Path, size: Optional[int], sha256: Optional[str]) -> Tuple[bool, str]:
    if not path.is_file():
        return False, "缺失"
    actual = path.stat().st_size
    if size is not None and actual != size:
        return False, f"大小不符（本地 {actual} / 期望 {size}）"
    if sha256:
        got = _sha256(path)
        if got.lower() != sha256.lower():
            return False, f"sha256 不符（本地 {got[:12]}… / 期望 {sha256[:12]}…）"
    return True, "OK"


def download(url: str, dest: Path, proxy: Optional[str] = None, timeout: int = 60) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers) if handlers else urllib.request.build_opener()

    req = urllib.request.Request(url, headers={"User-Agent": "sassy-cat-tts/1.0"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with opener.open(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_pct = -10
        with tmp.open("wb") as out:
            while True:
                block = resp.read(CHUNK)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if total:
                    pct = int(done * 100 / total)
                    if pct >= last_pct + 10:
                        last_pct = pct
                        print(f"      {pct:3d}%  {done / 1048576:6.1f}/{total / 1048576:.1f} MB", flush=True)
                else:
                    print(f"      {done / 1048576:6.1f} MB", flush=True)
    tmp.replace(dest)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def load_config(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_files(cfg: Dict, only: Optional[str]) -> Iterable[Tuple[Dict, Dict]]:
    for src in cfg.get("sources", []):
        if only and src.get("id") != only:
            continue
        for f in src.get("files", []):
            yield src, f


def cmd_list(cfg: Dict, vendor: Path, endpoint: str) -> int:
    total_bytes = 0
    print(f"vendor_dir = {vendor}")
    print(f"endpoint   = {endpoint}\n")
    for src in cfg.get("sources", []):
        size = sum(f.get("size", 0) for f in src.get("files", []))
        total_bytes += size
        flag = "可商用" if src.get("commercial_ok") else "禁止商用/未授权"
        print(f"[{src['id']}]  {src.get('title', '')}")
        print(f"    版本    : {src.get('version', '?')}")
        print(f"    授权    : {src.get('license', '?')}   ({flag})")
        print(f"    主页    : {src.get('homepage', '')}")
        print(f"    文件数  : {len(src.get('files', []))}，共 {size / 1048576:.1f} MB")
    print(f"\n合计 {total_bytes / 1048576:.1f} MB")
    print("\n全部文件的直链：")
    for src in cfg.get("sources", []):
        for f in src.get("files", []):
            print(f"  {build_url(endpoint, src['repo'], f['remote'])}")
    return 0


def cmd_fetch(
    cfg: Dict,
    vendor: Path,
    endpoint: str,
    proxy: Optional[str],
    only: Optional[str],
    verify_only: bool,
) -> int:
    ok = skipped = failed = 0
    failures: List[str] = []

    for src, f in iter_files(cfg, only):
        local = vendor / f["local"]
        url = build_url(endpoint, src["repo"], f["remote"])
        good, why = verify_file(local, f.get("size"), f.get("sha256"))

        if good:
            print(f"[跳过] {f['local']}（已存在且校验通过）")
            skipped += 1
            continue

        if verify_only:
            print(f"[异常] {f['local']}：{why}")
            failures.append(f"{f['local']}: {why}")
            failed += 1
            continue

        print(f"[下载] {f['local']}")
        print(f"       <- {url}")
        try:
            download(url, local, proxy=proxy)
        except Exception as e:
            print(f"       失败: {type(e).__name__}: {e}")
            failures.append(f"{f['local']}: 下载失败 {e}")
            failed += 1
            continue

        good, why = verify_file(local, f.get("size"), f.get("sha256"))
        if good:
            print("       校验通过")
            ok += 1
        else:
            print(f"       校验失败: {why}")
            failures.append(f"{f['local']}: {why}")
            failed += 1

    print(f"\n完成：下载 {ok}，跳过 {skipped}，失败 {failed}")
    if failures:
        print("失败明细：")
        for x in failures:
            print(f"  - {x}")
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_stdout()
    p = argparse.ArgumentParser(description="下载 / 校验 GPT-SoVITS 音色")
    p.add_argument("--config", help="voices.json 路径")
    p.add_argument("--vendor", help="GPT-SoVITS 仓库根目录（默认自动探测）")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"下载站，默认 {DEFAULT_ENDPOINT}")
    p.add_argument("--proxy", help="例如 http://localhost:11081（也可用 HTTPS_PROXY 环境变量）")
    p.add_argument("--only", help="只处理某个 source id")
    p.add_argument("--list", action="store_true", help="只打印清单和直链")
    p.add_argument("--verify", action="store_true", help="只校验，不下载")
    args = p.parse_args(argv)

    cfg_path = Path(args.config) if args.config else _default_config_path()
    if not cfg_path.is_file():
        print(f"找不到配置: {cfg_path}")
        return 2
    cfg = load_config(cfg_path)

    vendor = Path(args.vendor) if args.vendor else (
        Path(cfg["vendor_dir"]) if cfg.get("vendor_dir") else resolve_vendor_dir()
    )

    endpoint = args.endpoint.rstrip("/")
    proxy = args.proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

    if args.list:
        return cmd_list(cfg, vendor, endpoint)

    if not (vendor / "GPT_SoVITS").is_dir() and not args.verify:
        print(f"警告：{vendor} 下没有 GPT_SoVITS 目录，下载会创建权重目录，但代码还没就位。")
        print("      用 --vendor 指定，或设置 GSV_VENDOR_DIR，或把仓库放到 vendor/gpt-sovits。")

    return cmd_fetch(cfg, vendor, endpoint, proxy, args.only, args.verify)


if __name__ == "__main__":
    sys.exit(main())