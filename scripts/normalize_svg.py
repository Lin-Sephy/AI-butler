"""白鼬 SVG 颜色归一脚本 (2026-04-17)

锚点：
- 身体白  #FAFAF9 (cute)
- 眼黑/尾尖 #090A0A (cute 最深黑)
- 鼻/耳粉 #F5B1AF (front)

策略：
- cute 原样保留（锚点源头）
- 其他 3 张：每个 fill 色找最近的锚点，距离 < threshold 就归一
- 阈值：白 100 / 黑 50 / 粉 60（曼哈顿距离）
- 远离所有锚点的色（阴影、胡须、trace 边缘）不动

输出：frontend/src/assets/normalized/stoat-*.svg
原文件不改。
"""

import re
import shutil
import collections
from pathlib import Path

ASSETS = Path("frontend/src/assets")
OUTPUT = ASSETS / "normalized"
OUTPUT.mkdir(exist_ok=True)

ANCHORS = {
    "white": (0xFA, 0xFA, 0xF9),
    "black": (0x09, 0x0A, 0x0A),
    "pink":  (0xF5, 0xB1, 0xAF),
}
THRESHOLDS = {"white": 100, "black": 50, "pink": 60}

CUTE_FILE = "stoat-cute.svg"

color_re = re.compile(r'#([0-9a-fA-F]{6})')


def hex_to_rgb(h):
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb):
    return "#" + "".join(f"{x:02X}" for x in rgb)


def nearest_anchor(rgb):
    best = None
    for name, arg in ANCHORS.items():
        dist = sum(abs(a - b) for a, b in zip(rgb, arg))
        if dist < THRESHOLDS[name]:
            if best is None or dist < best[2]:
                best = (name, arg, dist)
    return best


def normalize_text(text):
    stats = collections.Counter()

    def repl(m):
        h = m.group(1).upper()
        rgb = hex_to_rgb(h)
        match = nearest_anchor(rgb)
        if match:
            stats[match[0]] += 1
            return rgb_to_hex(match[1])
        stats["kept"] += 1
        return m.group(0)

    new_text = color_re.sub(repl, text)
    return new_text, stats


print(f"输入: {ASSETS}")
print(f"输出: {OUTPUT}\n")

for svg in sorted(ASSETS.glob("stoat-*.svg")):
    out_path = OUTPUT / svg.name
    original = svg.read_text(encoding="utf-8")

    if svg.name == CUTE_FILE:
        shutil.copy(svg, out_path)
        total = len(color_re.findall(original))
        print(f"  {svg.name}: 原样保留（锚点源头），{total} fill")
        continue

    normalized, stats = normalize_text(original)
    out_path.write_text(normalized, encoding="utf-8")

    orig_unique = len(set(c.upper() for c in color_re.findall(original)))
    new_unique = len(set(c.upper() for c in color_re.findall(normalized)))

    print(f"  {svg.name}: {orig_unique} -> {new_unique} 种独立色")
    print(f"    -> 白: {stats.get('white', 0)}   -> 黑: {stats.get('black', 0)}   -> 粉: {stats.get('pink', 0)}   保留: {stats.get('kept', 0)}")

print("\n脚本跑完。原文件未改，归一版在 normalized/ 目录。")
