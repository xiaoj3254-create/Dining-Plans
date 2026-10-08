"""生成线性（outline）风格图标。

1) TabBar 图标：灰/橙两态，81x81 PNG（4x 超采样抗锯齿）
2) 页面小图标：location / clock / search，48x48 PNG，灰色线性

运行：C:\\Users\\Jerry\\.workbuddy\\binaries\\python\\versions\\3.13.12\\python.exe gen_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

TABBAR = Path(__file__).resolve().parent.parent / "src" / "static" / "tabbar"
ICONS = Path(__file__).resolve().parent.parent / "src" / "static" / "icons"
TABBAR.mkdir(parents=True, exist_ok=True)
ICONS.mkdir(parents=True, exist_ok=True)

GRAY = (178, 178, 178, 255)  # #b2b2b2 tabbar 未选中
PRIMARY = (108, 92, 231, 255)  # #6c5ce7 主色，tabbar 选中态
WHITE = (255, 255, 255, 255)
SOFT = (154, 160, 168, 255)  # 卡片行小图标灰
S = 324  # 81 * 4


def canvas(size=S):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


# ---------------- TabBar：线性风格 ----------------

def person_outline(d, cx, cy, scale=1.0, c=GRAY, w=20):
    r = int(40 * scale)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=c, width=w)
    bw, bh = int(60 * scale), int(62 * scale)
    top = cy + int(24 * scale)
    d.arc((cx - bw, top, cx + bw, top + bh * 2), 180, 360, fill=c, width=w)


def icon_plaza(d, c):
    """广场：饭碗 + 双筷（线性）"""
    d.line([(132, 36), (208, 124)], fill=c, width=20)
    d.line([(198, 26), (250, 100)], fill=c, width=20)
    d.rounded_rectangle((52, 156, 272, 182), radius=13, fill=c)  # 碗沿
    d.arc((80, 172, 244, 308), 0, 180, fill=c, width=22)  # 碗身轮廓


def icon_team(d, c):
    """组队：双人轮廓"""
    person_outline(d, 205, 96, 0.86, c)
    person_outline(d, 118, 108, 1.0, c)


def icon_message(d, c):
    """消息：气泡轮廓 + 三点"""
    d.rounded_rectangle((44, 66, 280, 212), radius=52, outline=c, width=22)
    d.line([(116, 208), (116, 262)], fill=c, width=20)
    d.line([(116, 262), (172, 210)], fill=c, width=20)
    for x in (112, 162, 212):
        d.ellipse((x - 14, 125, x + 14, 153), fill=c)


def icon_me(d, c):
    """我的：单人轮廓"""
    person_outline(d, 162, 92, 1.05, c)


TAB_ICONS = {"plaza": icon_plaza, "team": icon_team, "message": icon_message, "me": icon_me}


# ---------------- 页面小图标：48px 线性 ----------------

def small_location(d, c):
    """定位 Pin 轮廓"""
    d.ellipse((60, 28, 132, 100), outline=c, width=14)
    d.line([(80, 92), (96, 152)], fill=c, width=14)
    d.line([(112, 92), (96, 152)], fill=c, width=14)
    d.ellipse((86, 54, 106, 74), fill=c)


def small_clock(d, c):
    """时钟轮廓"""
    d.ellipse((28, 28, 164, 164), outline=c, width=14)
    d.line([(96, 96), (96, 58)], fill=c, width=12)
    d.line([(96, 96), (126, 112)], fill=c, width=12)


def small_search(d, c):
    """放大镜轮廓"""
    d.ellipse((34, 34, 130, 130), outline=c, width=14)
    d.line([(118, 118), (158, 158)], fill=c, width=16)


SMALL_ICONS = {"location": small_location, "clock": small_clock, "search": small_search}


def main():
    for name, fn in TAB_ICONS.items():
        for suffix, color in (("", GRAY), ("-active", PRIMARY)):
            img, d = canvas()
            fn(d, color)
            img = img.resize((81, 81), Image.LANCZOS)
            path = TABBAR / f"{name}{suffix}.png"
            img.save(path, optimize=True)
            print("saved", path)
    for name, fn in SMALL_ICONS.items():
        img, d = canvas(192)
        fn(d, SOFT)
        img = img.resize((48, 48), Image.LANCZOS)
        path = ICONS / f"{name}.png"
        img.save(path, optimize=True)
        print("saved", path)


if __name__ == "__main__":
    main()
