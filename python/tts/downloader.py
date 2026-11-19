# -*- coding: utf-8 -*-
"""基础模型 / 音色权重的按需下载。

设计目标
--------
- **权重不进 git，也不进安装包**：用户在设置页开启本地语音时才触发下载
- 下载全部落到 ``models_dir``（默认是 GPT-SoVITS 仓库根；正式打包时指向 userData）
- 支持**进度上报 / 取消 / 跳过已存在且校验通过的文件**
- 只用标准库（urllib / zipfile），不额外引入依赖

下载源来自 ``voices.json`` 的 ``sources``（音色）与 ``base_models``（基础模型）两段清单。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CHUNK = 1 << 20  # 1 MiB
DEFAULT_ENDPOINT = "https://huggingface.co"

#: 视为“推理必需”的基础包
REQUIRED_PACKAGES = ("base-models", "g2pw")


# ---------------------------------------------------------------------------
# 清单
# ---------------------------------------------------------------------------


def _voices_config_path() -> Path:
    return Path(__file__).resolve().parent / "voices.json"


def load_manifest() -> Dict[str, Any]:
    return json.loads(_voices_config_path().read_text(encoding="utf-8"))


def build_url(endpoint: str, repo: str, remote: str) -> str:
    seg = "/".join(urllib.parse.quote(p, safe="") for p in str(remote).split("/"))
    return f"{endpoint.rstrip('/')}/{repo}/resolve/main/{seg}"


@dataclass
class PlanItem:
    key: str
    local: Path
    url: str
    size: Optional[int] = None
    sha256: Optional[str] = None
    unzip: bool = False
    #: "models" → 落到 models_dir；"code" → 落到 vendor_dir
    #: （G2PW 这类由代码按相对路径加载的资源必须放在代码目录）
    root: str = "models"

    def resolve(self, code_root: Path, models_root: Path) -> Path:
        return (code_root if self.root == "code" else models_root) / self.local


def build_plan(packages: Optional[List[str]] = None) -> List[PlanItem]:
    """把清单展开成下载计划。

    :param packages: 只下载这些 source id；None 表示基础包 + 全部音色
    """
    cfg = load_manifest()
    endpoint = cfg.get("endpoint") or DEFAULT_ENDPOINT
    groups = list(cfg.get("base_models") or []) + list(cfg.get("sources") or [])

    if packages is None:
        packages = [g["id"] for g in groups]

    plan: List[PlanItem] = []
    for group in groups:
        if group.get("id") not in packages:
            continue
        ep = group.get("endpoint") or endpoint
        for f in group.get("files", []):
            plan.append(
                PlanItem(
                    key=f"{group['id']}:{f['local']}",
                    local=Path(f["local"]),
                    url=build_url(ep, group["repo"], f["remote"]),
                    size=f.get("size"),
                    sha256=f.get("sha256"),
                    unzip=bool(f.get("unzip")),
                    root=group.get("root", "models"),
                )
            )
    return plan


# ---------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------


@dataclass
class DownloadState:
    state: str = "idle"           # idle | running | done | failed | cancelled
    total_files: int = 0
    done_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    total_bytes: int = 0
    done_bytes: int = 0
    current_file: str = ""
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    log: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        percent = 0.0
        if self.total_bytes:
            percent = min(100.0, round(self.done_bytes * 100.0 / self.total_bytes, 1))
        return {
            "state": self.state,
            "totalFiles": self.total_files,
            "doneFiles": self.done_files,
            "skippedFiles": self.skipped_files,
            "failedFiles": self.failed_files,
            "totalBytes": self.total_bytes,
            "doneBytes": self.done_bytes,
            "percent": percent,
            "currentFile": self.current_file,
            "error": self.error,
            "log": self.log[-8:],
        }


_state = DownloadState()
_cancel = threading.Event()
_task: Optional[asyncio.Task] = None
_lock = threading.Lock()


def status() -> Dict[str, Any]:
    with _lock:
        return _state.to_dict()


def is_running() -> bool:
    return _task is not None and not _task.done()


# ---------------------------------------------------------------------------
# 校验与下载
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def verify(path: Path, size: Optional[int], sha256: Optional[str]) -> bool:
    if not path.is_file():
        return False
    if size is not None and path.stat().st_size != size:
        return False
    if sha256:
        return _sha256(path).lower() == sha256.lower()
    return True


def _download_to(url: str, dest: Path, proxy: Optional[str]) -> None:
    """单文件下载（含进度与取消），直接写绝对路径。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)

    req = urllib.request.Request(url, headers={"User-Agent": "sassy-cat-tts/1.0"})
    with opener.open(req, timeout=60) as resp, tmp.open("wb") as out:
        while True:
            if _cancel.is_set():
                raise RuntimeError("cancelled")
            block = resp.read(CHUNK)
            if not block:
                break
            out.write(block)
            with _lock:
                _state.done_bytes += len(block)
    tmp.replace(dest)


def _extract_zip(zip_path: Path, target_dir: Path) -> None:
    """解压 G2PW 这类“整包发布”的资源，兼容 zip 内是否带一层同名目录。"""
    tmp_dir = target_dir.with_suffix(target_dir.suffix + ".unzip")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp_dir)

    children = list(tmp_dir.iterdir())
    src = children[0] if len(children) == 1 and children[0].is_dir() else tmp_dir
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if src == tmp_dir:
        tmp_dir.rename(target_dir)
    else:
        src.rename(target_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _run_plan(code_root: Path, models_root: Path, plan: List[PlanItem], proxy: Optional[str]) -> None:
    """阻塞执行整个计划（在线程里跑）。"""
    for item in plan:
        if _cancel.is_set():
            raise RuntimeError("cancelled")

        dest = item.resolve(code_root, models_root)
        label = str(dest)

        # 已存在的目录型资源（G2PW）：看目录非空就跳过
        if item.unzip and dest.is_dir() and any(dest.iterdir()):
            with _lock:
                _state.skipped_files += 1
                _state.done_bytes += item.size or 0
                _state.log.append(f"跳过 {label}（已存在）")
            continue
        if not item.unzip and verify(dest, item.size, item.sha256):
            with _lock:
                _state.skipped_files += 1
                _state.done_bytes += item.size or 0
                _state.log.append(f"跳过 {label}（校验通过）")
            continue

        with _lock:
            _state.current_file = label
            _state.log.append(f"下载 {label}")
        logger.info("下载 %s <- %s", label, item.url)

        if item.unzip:
            zip_path = dest.with_suffix(dest.suffix + ".zip")
            _download_to(item.url, zip_path, proxy)
            _extract_zip(zip_path, dest)
            try:
                zip_path.unlink()
            except OSError:
                pass
        else:
            _download_to(item.url, dest, proxy)

        if not item.unzip and not verify(dest, item.size, item.sha256):
            raise RuntimeError(f"{label} 校验失败")

        with _lock:
            _state.done_files += 1
            _state.log.append(f"完成 {label}")


async def _run_async(
    code_root: Path, models_root: Path, plan: List[PlanItem], proxy: Optional[str]
) -> None:
    global _task
    try:
        await asyncio.to_thread(_run_plan, code_root, models_root, plan, proxy)
        with _lock:
            _state.state = "done"
            _state.finished_at = time.time()
            _state.current_file = ""
        logger.info("模型下载完成")
    except RuntimeError as e:
        cancelled = str(e) == "cancelled"
        with _lock:
            _state.state = "cancelled" if cancelled else "failed"
            _state.error = None if cancelled else str(e)
            _state.finished_at = time.time()
            _state.current_file = ""
        if not cancelled:
            logger.warning("模型下载失败: %s", e)
    except Exception as e:  # noqa: BLE001
        with _lock:
            _state.state = "failed"
            _state.error = f"{type(e).__name__}: {e}"
            _state.finished_at = time.time()
            _state.current_file = ""
        logger.exception("模型下载异常")


def _reset_state(plan: List[PlanItem]) -> None:
    """在启动任务**之前**就把状态置为 running，避免前端首次读到 idle 而误判。"""
    with _lock:
        _state.state = "running"
        _state.started_at = time.time()
        _state.finished_at = None
        _state.error = None
        _state.total_files = len(plan)
        _state.done_files = 0
        _state.skipped_files = 0
        _state.failed_files = 0
        _state.total_bytes = sum(i.size or 0 for i in plan)
        _state.done_bytes = 0
        _state.current_file = ""
        _state.log = []


def start(
    code_root: Path,
    models_root: Path,
    packages: Optional[List[str]] = None,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    """启动下载（非阻塞）。重复调用时返回当前状态。"""
    global _task
    if is_running():
        return status()

    _cancel.clear()
    plan = build_plan(packages)
    if not plan:
        with _lock:
            _state.state = "failed"
            _state.error = "下载清单为空"
        return status()

    _reset_state(plan)
    loop = asyncio.get_running_loop()
    _task = loop.create_task(_run_async(code_root, models_root, plan, proxy))
    return status()


def cancel() -> Dict[str, Any]:
    _cancel.set()
    return status()


def missing_required(code_root: Path, models_root: Path) -> List[str]:
    """返回仍然缺失的必需文件（供 /status 判断是否要先下载）。"""
    plan = build_plan(list(REQUIRED_PACKAGES))
    missing = []
    for item in plan:
        dest = item.resolve(code_root, models_root)
        if item.unzip:
            if not (dest.is_dir() and any(dest.iterdir())):
                missing.append(str(dest))
        elif not verify(dest, item.size, item.sha256):
            missing.append(str(dest))
    return missing