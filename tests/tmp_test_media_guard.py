# -*- coding: utf-8 -*-
"""Media guard regression: keep all images by default, compress; offload only over budget.

Run: .venv\\Scripts\\python.exe tests\\tmp_test_media_guard.py
"""

import asyncio
import base64
import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python")))

from PIL import Image
from langchain_core.messages import HumanMessage

from agent import middlewares

FAILED = []


def check(name, cond, detail=""):
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  | {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def image_block(width=900, height=600, noise=False):
    if noise:
        img = Image.effect_noise((width, height), 120).convert("RGB")
    else:
        img = Image.new("RGB", (width, height), (235, 235, 235))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "type": "image",
        "base64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "mime_type": "image/png",
    }


def message(text, block):
    return HumanMessage(id=f"m-{text}", content=[{"type": "text", "text": text}, block])


def payload(b):
    return middlewares._payload_bytes(b)


def media_blocks(msg):
    return [b for b in msg.content if middlewares._media_payload(b) is not None]


async def run_middleware(messages):
    return await middlewares.trim_media_history.abefore_model({"messages": messages}, None)


async def run():
    conf = {
        "max_bytes": 300 * 1024,
        "max_px": 800,
        "budget_bytes": 8 * 1024 * 1024,
        "budget_images": 24,
        "offload_bytes": 1024 * 1024,
    }
    old = middlewares._media_guard_config
    middlewares._media_guard_config = lambda: dict(conf)
    try:
        # 1) Default: keep all 5 images, compress only
        msgs = [message(f"u{i}", image_block(noise=True)) for i in range(5)]
        result = await run_middleware(msgs)
        new = result["messages"] if result else msgs
        check(
            "keep all 5 images by default",
            sum(len(media_blocks(m)) for m in new) == 5,
            str([len(media_blocks(m)) for m in new]),
        )
        check(
            "images re-encoded as JPEG",
            all(b.get("mime_type") == "image/jpeg" for m in new for b in media_blocks(m)),
        )
        check(
            "single image near target",
            all(payload(b) <= 320 * 1024 for m in new for b in media_blocks(m)),
            str([payload(b) // 1024 for m in new for b in media_blocks(m)]),
        )

        # 2) Idempotent
        again = await run_middleware(new)
        check("second pass is a no-op", again is None)

        # 3) Image count budget: 5 images, budget 2 -> keep newest 2, older become placeholders
        conf["budget_images"] = 2
        msgs = [message(f"b{i}", image_block()) for i in range(5)]
        result = await run_middleware(msgs)
        new = result["messages"] if result else msgs
        kept = [b for m in new for b in media_blocks(m)]
        elided = [
            b
            for m in new
            for b in m.content
            if b.get("type") == "text"
            and b.get("text", "").startswith(middlewares.MEDIA_ELIDED_PREFIX)
        ]
        check("image count budget keeps newest 2", len(kept) == 2, str(len(kept)))
        check("old images become placeholders", len(elided) == 3, str(len(elided)))
        check(
            "original text blocks remain",
            all(
                any(
                    b.get("type") == "text"
                    and not b.get("text", "").startswith(middlewares.MEDIA_ELIDED_PREFIX)
                    for b in m.content
                )
                for m in new
            ),
        )

        # 4) Budget 0 -> keep everything
        conf["budget_images"] = 0
        conf["budget_bytes"] = 0
        msgs = [message(f"z{i}", image_block()) for i in range(5)]
        result = await run_middleware(msgs)
        new = result["messages"] if result else msgs
        check("zero budget keeps all", sum(len(media_blocks(m)) for m in new) == 5)
    finally:
        middlewares._media_guard_config = old


if __name__ == "__main__":
    asyncio.run(run())
    print("FAILED:", FAILED)
    sys.exit(1 if FAILED else 0)

