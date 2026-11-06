"""把 scripts/readme-shots.js 抓到的原始截图，加工成 README 使用的配图。

用法：
    npx vite                        # 另开一个终端
    electron scripts/readme-shots.js
    python scripts/make-readme-images.py

产物：docs/screenshots/{dashboard,chat,skills,knowledge-base,desktop-pet}.jpg
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import numpy as np
import os

SRC = 'shots/readme-raw'
DST = 'docs/screenshots'
os.makedirs(DST, exist_ok=True)


def save_jpg(im: Image.Image, name: str, quality: int = 90):
    path = os.path.join(DST, f'{name}.jpg')
    im.convert('RGB').save(path, 'JPEG', quality=quality, optimize=True, progressive=True)
    print(f'{name}.jpg  {os.path.getsize(path) / 1024:.0f} KB  {im.size[0]}x{im.size[1]}')


# ---------- 1. 页面截图：裁掉多余空白并压缩 ----------
# 知识库页下半部基本是空的，裁成「页头 + 一行卡片」的横幅
kb = Image.open(os.path.join(SRC, 'kb.png')).crop((0, 0, 1440, 430))
save_jpg(kb, 'knowledge-base')

for name in ('dashboard', 'chat', 'skills'):
    save_jpg(Image.open(os.path.join(SRC, f'{name}.png')), name)


# ---------- 2. 桌宠海报：透明底精灵 + 品牌暖色卡片 + 示例气泡 ----------
W, H = 900, 620
BG_TOP = (251, 240, 218)
BG_BOTTOM = (233, 210, 166)
INK = (44, 33, 19)
AMBER = (239, 168, 76)

bg = Image.new('RGB', (W, H), BG_TOP)
top = np.array(BG_TOP, dtype=np.float32)
bottom = np.array(BG_BOTTOM, dtype=np.float32)
for y in range(H):
    t = y / (H - 1)
    bg.paste(tuple(int(c) for c in (top * (1 - t) + bottom * t)), (0, y, W, y + 1))

# 顶部柔光
glow = Image.new('L', (W, H), 0)
ImageDraw.Draw(glow).ellipse((-160, -260, W + 160, 260), fill=90)
glow = glow.filter(ImageFilter.GaussianBlur(120))
bg.paste(Image.new('RGB', (W, H), (255, 249, 236)), (0, 0), glow)

# 细网格
grid = Image.new('RGBA', (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(grid)
for x in range(0, W, 48):
    gd.line([(x, 0), (x, H)], fill=(180, 140, 80, 10))
for y in range(0, H, 48):
    gd.line([(0, y), (W, y)], fill=(180, 140, 80, 10))
bg = Image.alpha_composite(bg.convert('RGBA'), grid)

# 精灵：透明通道直接使用；若拿到白底图则按亮度抠像
pet = Image.open(os.path.join(SRC, 'pet.png')).convert('RGBA')
alpha_channel = np.array(pet)[:, :, 3]
if alpha_channel.min() < 250:
    pet_img = pet
else:
    arr = np.array(pet.convert('RGB')).astype(np.int16)
    alpha = np.clip((255 - arr.min(axis=2)) * 4, 0, 255).astype(np.uint8)
    pet_img = Image.fromarray(np.dstack([arr.astype(np.uint8), alpha]), 'RGBA')

pet_img = pet_img.crop(pet_img.getbbox())
target_h = 300
ratio = target_h / pet_img.height
pet_img = pet_img.resize((int(pet_img.width * ratio), target_h), Image.LANCZOS)

px = (W - pet_img.width) // 2
py = H - pet_img.height - 70

shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
ImageDraw.Draw(shadow).ellipse(
    (px + 10, py + pet_img.height - 26, px + pet_img.width - 10, py + pet_img.height + 16),
    fill=(120, 80, 30, 90),
)
bg = Image.alpha_composite(bg, shadow.filter(ImageFilter.GaussianBlur(18)))
bg.alpha_composite(pet_img, (px, py))

# 气泡
bubble_text = '本喵在呢，今天想聊点什么？'
font = ImageFont.truetype(r'C:\Windows\Fonts\msyhbd.ttc', 28)
small = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 18)
tw = int(font.getlength(bubble_text))
bw, bh = tw + 76, 92
bx, by = (W - bw) // 2, py - bh - 36

overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)
od.rounded_rectangle((bx + 6, by + 8, bx + bw + 6, by + bh + 8), radius=24, fill=(120, 80, 30, 28))
od.rounded_rectangle((bx, by, bx + bw, by + bh), radius=24, fill=(255, 252, 244, 255), outline=AMBER + (110,), width=2)
od.polygon([(W // 2 - 14, by + bh - 2), (W // 2 + 14, by + bh - 2), (W // 2, by + bh + 20)], fill=(255, 252, 244, 255))
od.line([(W // 2 - 14, by + bh - 2), (W // 2, by + bh + 20), (W // 2 + 14, by + bh - 2)], fill=AMBER + (110,), width=2)
bg = Image.alpha_composite(bg, overlay)

d = ImageDraw.Draw(bg)
d.text((bx + 34, by + 18), bubble_text, font=font, fill=INK)
d.text((bx + 34, by + 56), 'Alt + Shift + Q  ·  随手问一句', font=small, fill=(150, 116, 64))

save_jpg(bg, 'desktop-pet', quality=92)
