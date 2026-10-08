"""生成餐馆/菜品占位图（统一风格：菜系主题色底 + 圆盘 + 名称）。

数据来源与 seed 共用一份清单：backend/scripts/menu_catalog.json
输出：src/static/food/*.png（256x256 PNG）+ _default.png

运行：C:\\Users\\Jerry\\.workbuddy\\binaries\\python\\versions\\3.13.12\\python.exe gen_food_images.py
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent          # frontend/
OUT = ROOT / "src" / "static" / "food"
CATALOG = ROOT.parent / "backend" / "scripts" / "menu_catalog.json"

SS = 512            # 超采样画布
SIZE = 192          # 出图尺寸（小程序包体积敏感：192² + 颜色量化 ≈ 每张 3-4KB）
QUANTIZE_COLORS = 64
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"

# 菜系主题色（与紫色主色系统和谐，同时保持区分度）
CUISINE_COLOR = {
    "火锅": (232, 106, 92),
    "烤肉": (201, 123, 74),
    "日料": (91, 141, 184),
    "川菜": (217, 83, 79),
    "粤菜": (107, 175, 141),
    "西餐": (140, 123, 166),
    "快餐": (224, 163, 62),
    "素食": (127, 174, 90),
}
FALLBACK_COLOR = (108, 92, 231)  # 主色


def tint(rgb, ratio: float):
    """与白色混合，ratio=0 全白，1 原色"""
    return tuple(int(255 - (255 - c) * ratio) for c in rgb)


def font(size: int, bold: bool = True):
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size, index=0)
    except Exception:
        return ImageFont.load_default()


def split_lines(name: str, per_line: int = 5) -> list[str]:
    """名称过长时折行（中文按字符数切分）"""
    if len(name) <= per_line:
        return [name]
    return [name[:per_line], name[per_line:per_line * 2]]


def save(img: Image.Image, filename: str):
    OUT.mkdir(parents=True, exist_ok=True)
    out = img.resize((SIZE, SIZE), Image.LANCZOS).convert("RGB")
    # 纯色图形 + 文字：颜色量化后 PNG 体积可降 60%+，肉眼几乎无差别
    out.quantize(colors=QUANTIZE_COLORS).save(OUT / filename, optimize=True)


def draw_dish(name: str, cuisine: str, filename: str):
    """菜品图：浅色底 + 菜系色圆盘 + 菜名"""
    color = CUISINE_COLOR.get(cuisine, FALLBACK_COLOR)
    img = Image.new("RGB", (SS, SS), tint(color, 0.16))
    d = ImageDraw.Draw(img)
    # 盘子
    cx = cy = SS // 2
    d.ellipse((cx - 150, cy - 150, cx + 150, cy + 150), fill=color)
    d.ellipse((cx - 118, cy - 118, cx + 118, cy + 118), outline=tint(color, 0.55), width=6)
    # 菜名
    lines = split_lines(name)
    f = font(58 if len(lines) == 1 else 52)
    step = 66
    start = cy - step * (len(lines) - 1) / 2
    for i, line in enumerate(lines):
        d.text((cx, start + i * step), line, font=f, fill=(255, 255, 255), anchor="mm")
    save(img, filename)


def draw_restaurant(name: str, district: str, cuisine: str, filename: str):
    """餐馆图：菜系色实底 + 店名 + 商圈"""
    color = CUISINE_COLOR.get(cuisine, FALLBACK_COLOR)
    img = Image.new("RGB", (SS, SS), color)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, SS, 96), fill=tint(color, 0.82))
    d.text((36, 48), cuisine, font=font(40), fill=(255, 255, 255), anchor="lm")

    lines = split_lines(name, 6)
    f = font(56 if len(lines) == 1 else 50)
    step = 62
    start = SS // 2 - 10 - step * (len(lines) - 1) / 2
    for i, line in enumerate(lines):
        d.text((SS // 2, start + i * step), line, font=f, fill=(255, 255, 255), anchor="mm")
    if district:
        d.text((SS // 2, SS - 66), district, font=font(38, bold=False),
               fill=tint(color, 0.35), anchor="mm")
    save(img, filename)


def draw_default():
    """缺图兜底：中性灰 + 餐具"""
    img = Image.new("RGB", (SS, SS), (239, 238, 246))
    d = ImageDraw.Draw(img)
    cx = cy = SS // 2
    d.ellipse((cx - 140, cy - 140, cx + 140, cy + 140), outline=(178, 178, 178), width=8)
    d.ellipse((cx - 96, cy - 96, cx + 96, cy + 96), outline=(198, 198, 214), width=6)
    save(img, "_default.png")


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    total = 0
    for cuisine, dishes in catalog["dish_pools"].items():
        for dish in dishes:
            draw_dish(dish["name"], cuisine, dish["file"])
            total += 1
    for r in catalog["restaurants"]:
        draw_restaurant(r["name"], r.get("district", ""), r["cuisine_type"], r["image"])
        total += 1
    draw_default()

    size_kb = sum(p.stat().st_size for p in OUT.glob("*.png")) // 1024
    print(f"生成 {total + 1} 张图片 → {OUT}")
    print(f"目录总体积：{size_kb} KB")
    if size_kb > 600:
        print("⚠ 体积超过 600KB，建议把 SIZE 降到 192 或对图片做 quantize")


if __name__ == "__main__":
    main()
