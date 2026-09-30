"""生成桌宠 spritesheet 占位资源（正式美术资源到位前的联调占位）。

用法：
    python scripts/gen_pet_sprites.py

依赖：
    Pillow（PIL）

说明：
    依据 pet/assets/sprites/cat/config.json 的 animations 键名与帧数，
    为每个动画生成一张「水平拼接、单帧 120x110、透明背景」的 PNG。
    帧数与 config.json 严格对齐，保证 CSS background-position 逐帧不越界。
    视觉上以简单灰猫形体 + 逐帧上下浮动 + 帧序号标记，便于肉眼确认帧序正确。
    正式美术资源就位后，直接覆盖同名 PNG 即可，无需改动任何代码。
"""

import json
import math
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITE_DIR = os.path.join(ROOT, "pet", "assets", "sprites", "cat")
CONFIG_PATH = os.path.join(SPRITE_DIR, "config.json")

# 与 SvgSpriteRenderer 保持一致的基础色
BODY = (100, 116, 139, 255)     # #64748b
INNER_EAR = (249, 168, 212, 255)  # #f9a8d4
EYE = (30, 41, 59, 255)         # #1e293b
WHISKER = (30, 41, 59, 255)     # #1e293b
ACCENT = (99, 102, 241, 255)    # 帧序号标记色


def draw_frame(img, draw, ox, idx, total):
    """在帧内绘制一只简单灰猫；bob 为随帧正弦浮动（模拟呼吸/行走起伏）。"""
    bob = 3.0 * math.sin(2 * math.pi * (idx / max(total, 1)))

    def y(base):
        return base + bob

    cx = ox + 60
    # 尾巴（简化直线）
    draw.line([(cx + 32, y(84)), (cx + 52, y(66))], fill=BODY, width=8, joint="curve")
    # 身体
    draw.ellipse([cx - 34, y(76) - 26, cx + 34, y(76) + 26], fill=BODY)
    # 耳朵
    draw.polygon([(cx - 24, y(38)), (cx - 16, y(16)), (cx - 4, y(34))], fill=BODY)
    draw.polygon([(cx + 24, y(38)), (cx + 16, y(16)), (cx + 4, y(34))], fill=BODY)
    # 耳内
    draw.polygon([(cx - 20, y(33)), (cx - 15, y(21)), (cx - 9, y(31))], fill=INNER_EAR)
    draw.polygon([(cx + 20, y(33)), (cx + 15, y(21)), (cx + 9, y(31))], fill=INNER_EAR)
    # 头
    draw.ellipse([cx - 26, y(46) - 26, cx + 26, y(46) + 26], fill=BODY)
    # 眼睛
    draw.ellipse([cx - 13, y(43) - 4, cx - 5, y(43) + 4], fill=EYE)
    draw.ellipse([cx + 5, y(43) - 4, cx + 13, y(43) + 4], fill=EYE)
    # 胡须
    for dy in (-3, 4):
        draw.line([(cx - 30, y(48) + dy), (cx - 18, y(48) + dy - 1)], fill=WHISKER, width=1)
        draw.line([(cx + 30, y(48) + dy), (cx + 18, y(48) + dy - 1)], fill=WHISKER, width=1)
    # 帧序号标记（左上角，便于肉眼确认帧序）
    draw.text((ox + 4, 4), f"{idx + 1}/{total}", fill=ACCENT)


def generate():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    fw = config["frameWidth"]
    fh = config["frameHeight"]
    animations = config["animations"]

    os.makedirs(SPRITE_DIR, exist_ok=True)

    written = []
    for name, spec in animations.items():
        frames = int(spec["frames"])
        sheet = Image.new("RGBA", (fw * frames, fh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        for i in range(frames):
            draw_frame(sheet, draw, i * fw, i, frames)
        out_path = os.path.join(SPRITE_DIR, f"{name}.png")
        sheet.save(out_path)
        written.append((name, frames, fw * frames))

    print(f"已生成 {len(written)} 个占位 spritesheet -> {SPRITE_DIR}")
    for name, frames, w in written:
        print(f"  {name:<14} frames={frames:<3} size={w}x{fh}")


if __name__ == "__main__":
    generate()