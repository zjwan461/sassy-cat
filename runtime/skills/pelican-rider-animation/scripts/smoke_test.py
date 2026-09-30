#!/usr/bin/env python3
"""Headless smoke test for a self-contained animated HTML file.

为什么需要它：
    一个 HTML 动画"打开是白屏 / 动不了"的原因，九成是运行时报错
    （ReferenceError、undefined 属性、几何算出 NaN）。肉眼看代码查不出来，
    但这里用一套桩 DOM + 桩 Canvas 把 <script> 真的跑起来，逐帧驱动，
    顺手注入键盘/指针交互，任何异常都会被抓住。

用法：
    python smoke_test.py path/to/animation.html
    python smoke_test.py path/to/animation.html --extra-js drive_extra.js

退出码 0 = 全部阶段通过；1 = 有阶段失败（异常 / 动画循环没续跑）。
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script\s*>", re.S | re.I)

# ----------------------------------------------------------------------------
# JS 桩环境：假 DOM / 假 Canvas / 可控时钟 / 手动 rAF 队列
# ----------------------------------------------------------------------------
HARNESS = r"""
'use strict';
const __noop = () => {};
const __grad = { addColorStop: __noop };

globalThis.__nanHits = 0;
globalThis.__canvas = null;
globalThis.__errors = [];

/* ---------- 假 2D context：未定义的方法一律 no-op，并统计 NaN 参数 ---------- */
function __makeCtx() {
  const base = {
    canvas: null,
    createLinearGradient: () => __grad,
    createRadialGradient: () => __grad,
    createConicGradient: () => __grad,
    createPattern: () => null,
    measureText: () => ({ width: 12, actualBoundingBoxAscent: 9, actualBoundingBoxDescent: 3 }),
    isPointInPath: () => false,
    getImageData: () => ({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
    putImageData: __noop,
    setTransform: __noop,
    resetTransform: __noop
  };
  return new Proxy(base, {
    get(t, k) {
      if (k in t) return t[k];
      // 未知方法 -> no-op，但顺手检查数字参数里有没有 NaN / Infinity
      return function () {
        for (let i = 0; i < arguments.length; i++) {
          const a = arguments[i];
          if (typeof a === 'number' && !Number.isFinite(a)) { globalThis.__nanHits++; break; }
        }
      };
    },
    set(t, k, v) {
      if (typeof v === 'number' && !Number.isFinite(v)) globalThis.__nanHits++;
      t[k] = v;
      return true;
    }
  });
}

/* ---------- 假 DOM 元素 ---------- */
function __makeEl(tag) {
  const t = (tag || 'div').toUpperCase();
  const el = {
    tagName: t, nodeName: t,
    style: {}, dataset: {}, children: [], childNodes: [],
    width: 900, height: 460,
    offsetWidth: 900, offsetHeight: 460,
    clientWidth: 900, clientHeight: 460,
    scrollWidth: 900, scrollHeight: 460,
    textContent: '', innerHTML: '', value: '',
    hidden: false,
    classList: { add: __noop, remove: __noop, toggle: __noop, contains: () => false },
    addEventListener: __noop, removeEventListener: __noop,
    __dispatch: () => 0,
    getContext() {
      if (!el.__ctx) { el.__ctx = __makeCtx(); el.__ctx.canvas = el; }
      globalThis.__canvas = el;              // 记住第一个拿到 context 的元素
      return el.__ctx;
    },
    getBoundingClientRect() {
      return { x: 0, y: 0, left: 0, top: 0, right: 900, bottom: 460, width: 900, height: 460 };
    },
    appendChild(c) { el.children.push(c); return c; },
    removeChild(c) { return c; },
    insertBefore(c) { el.children.push(c); return c; },
    setAttribute(k, v) { el[k] = v; },
    getAttribute() { return null; },
    hasAttribute() { return false; },
    removeAttribute: __noop,
    querySelector() { return null; },
    querySelectorAll() { return []; },
    focus: __noop, blur: __noop, click: __noop,
    setPointerCapture: __noop, releasePointerCapture: __noop,
    animate: () => ({ finished: Promise.resolve(), cancel: __noop })
  };
  __attachDispatcher(el);
  return el;
}

/* ---------- 事件派发器（可读取触发次数） ---------- */
function __attachDispatcher(obj) {
  const L = Object.create(null);
  obj.__listeners = L;
  obj.addEventListener = (type, fn) => { (L[type] = L[type] || []).push(fn); };
  obj.removeEventListener = (type, fn) => {
    const a = L[type]; if (!a) return;
    const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1);
  };
  obj.__dispatch = (type, ev) => {
    const fs = L[type] || [];
    for (const f of fs) {
      f(Object.assign({ type, target: obj, preventDefault: __noop, stopPropagation: __noop }, ev || {}));
    }
    return fs.length;
  };
  return obj;
}

/* ---------- document / window ---------- */
const __els = Object.create(null);
function __getEl(id) { if (!__els[id]) __els[id] = __makeEl('div'); return __els[id]; }

globalThis.document = __attachDispatcher({
  getElementById: __getEl,
  querySelector: (sel) => __getEl(sel),
  querySelectorAll: () => [],
  createElement: __makeEl,
  createElementNS: (_ns, tag) => __makeEl(tag),
  body: __makeEl('body'),
  documentElement: __makeEl('html'),
  hidden: false,
  visibilityState: 'visible'
});

globalThis.window = globalThis;
__attachDispatcher(globalThis);
globalThis.innerWidth = 1280;
globalThis.innerHeight = 800;
globalThis.devicePixelRatio = 1;
globalThis.matchMedia = () => ({
  matches: false, media: '', addEventListener: __noop, removeEventListener: __noop,
  addListener: __noop, removeListener: __noop
});
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' });

/* ---------- 可控时钟 ---------- */
let __t = 0;
const __EPOCH = 1700000000000;
globalThis.performance = { now: () => __t, timeOrigin: __EPOCH };
Date.now = () => __EPOCH + __t;

/* ---------- 手动 rAF 队列 ---------- */
let __raf = [];
globalThis.requestAnimationFrame = (cb) => { __raf.push(cb); return __raf.length; };
globalThis.cancelAnimationFrame = () => {};

/* ---------- 工具 ---------- */
globalThis.__fire = (type, ev) => {
  const targets = [globalThis, globalThis.document, globalThis.document.body, globalThis.__canvas];
  let n = 0;
  for (const t of targets) { if (t && typeof t.__dispatch === 'function') n += t.__dispatch(type, ev); }
  return n;
};
"""

# ----------------------------------------------------------------------------
# 驱动：分阶段跑帧，注入交互
# ----------------------------------------------------------------------------
RUNNER = r"""
/* ---------- 阶段驱动器 ---------- */
const __phases = [];

function __run(name, frames, dt, before) {
  const step = (dt === undefined) ? 16.7 : dt;
  try {
    if (before) before();
    let ran = 0;
    for (let i = 0; i < frames; i++) {
      const q = __raf; __raf = [];
      __t += step;
      for (const cb of q) { cb(__t); ran++; }
    }
    let status = 'PASS';
    const notes = [ran + ' frames'];
    if (ran === 0 && frames > 1) { status = 'FAIL'; notes.push('动画循环没有续跑：rAF 队列为空'); }
    else if (ran < frames * 0.8) { status = 'WARN'; notes.push('部分帧内 rAF 未续跑'); }
    __phases.push({ name, status, note: notes.join(' / ') });
  } catch (e) {
    __phases.push({ name, status: 'FAIL', note: String((e && e.stack) || e).split('\n').slice(0, 3).join(' | ') });
  }
}

/* 1. 加载脚本 */
try {
  new Function(__SRC)();
} catch (e) {
  console.error('❌ <script> 顶层执行异常：');
  console.error(String((e && e.stack) || e));
  process.exit(1);
}

if (__raf.length === 0) {
  console.error('❌ 脚本加载完没有调用 requestAnimationFrame —— 没有动画循环，至少确认它是不是纯 CSS 动画页。');
  process.exit(1);
}

if (__EXTRA_JS) { try { new Function(__EXTRA_JS)(); } catch (e) { console.error('extra-js 执行失败: ' + e); } }

const K_SPACE = { key: ' ', code: 'Space', keyCode: 32, which: 32 };
const K_P     = { key: 'p', code: 'KeyP', keyCode: 80, which: 80 };

/* 2. 标准交互剧本 */
__run('静置骑行 90 帧', 90);
__run('冲刺：pointerdown + mousedown + Space', 90, 16.7, () => {
  __fire('pointerdown', { button: 0, pointerId: 1, clientX: 450, clientY: 320 });
  __fire('mousedown',  { button: 0, clientX: 450, clientY: 320 });
  __fire('keydown', K_SPACE);
});
__run('松开：pointerup + mouseup + keyup', 60, 16.7, () => {
  __fire('pointerup', { button: 0, pointerId: 1 });
  __fire('mouseup',   { button: 0 });
  __fire('keyup', K_SPACE);
});
__run('暂停 (P)', 30, 16.7, () => __fire('keydown', K_P));
__run('暂停中静置 20 帧', 20);
__run('恢复 (P)', 30, 16.7, () => __fire('keydown', K_P));
__run('重置里程 (R)', 30, 16.7, () => __fire('keydown', { key: 'r', code: 'KeyR', keyCode: 82, which: 82 }));
__run('窗口尺寸变化', 20, 16.7, () => __fire('resize', { innerWidth: 800, innerHeight: 600 }));
__run('大 dt 保护 250ms x6（切标签页回来）', 6, 250);
__run('非整数 dt 60 帧', 60, 16.7 * 1.37);
__run('长时间静置 200 帧', 200);

/* 3. 报告 */
let failed = 0, warned = 0, total = 0;
console.log('');
for (const p of __phases) {
  total += parseInt(p.note, 10) || 0;
  const icon = p.status === 'PASS' ? '✅' : (p.status === 'WARN' ? '⚠️ ' : '❌');
  if (p.status === 'FAIL') failed++;
  if (p.status === 'WARN') warned++;
  console.log(icon + ' ' + p.name + '  →  ' + p.note);
}
console.log('');
console.log('帧数总计: ' + total + '  |  阶段: ' + __phases.length + '  |  失败: ' + failed + '  |  警告: ' + warned);
console.log('Canvas 非有限数值调用次数 (NaN/Infinity): ' + globalThis.__nanHits);
if (globalThis.__nanHits > 0) {
  console.log('❌ 检测到 NaN/Infinity —— 几何计算里有除零或未定义坐标，画面会消失。');
  failed++;
}
if (failed === 0) console.log('🎉 冒烟测试全部通过');
process.exit(failed === 0 ? 0 : 1);
"""


def extract_script(html: str) -> str:
    blocks = SCRIPT_RE.findall(html)
    if not blocks:
        sys.exit("❌ 没找到 <script> 块 —— 这可能是纯 CSS 动画页，冒烟测试不适用。")
    # 取最长的那个块：动画主逻辑通常在最后、且最长
    return max(blocks, key=len)


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless smoke test for an animated HTML file")
    ap.add_argument("html", help="待测 HTML 文件路径")
    ap.add_argument("--extra-js", help="额外驱动 JS 文件（自定义按键/交互）", default=None)
    ap.add_argument("--keep", action="store_true", help="保留临时 JS 文件以便手工调试")
    args = ap.parse_args()

    node = shutil.which("node")
    if not node:
        sys.exit("❌ 找不到 node，无法做无头冒烟测试。请安装 Node.js 或跳过这一步（但务必在浏览器里手点一遍）。")

    path = Path(args.html)
    if not path.is_file():
        sys.exit(f"❌ 文件不存在: {path}")

    src = extract_script(path.read_text(encoding="utf-8"))
    extra = ""
    if args.extra_js:
        extra = Path(args.extra_js).read_text(encoding="utf-8")

    bundle = (
        HARNESS
        + "\nconst __SRC = " + json.dumps(src) + ";\n"
        + "const __EXTRA_JS = " + json.dumps(extra) + ";\n"
        + RUNNER
    )

    tmp = Path(tempfile.gettempdir()) / f"smoke_{path.stem}.js"
    tmp.write_text(bundle, encoding="utf-8")

    print(f"🧪 冒烟测试: {path.name}  (提取脚本 {len(src)} 字符)")
    proc = subprocess.run([node, str(tmp)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(proc.stdout or "")
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    if not args.keep:
        tmp.unlink(missing_ok=True)
    else:
        print(f"(临时文件保留在 {tmp})")

    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())