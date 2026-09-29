"""
系统托盘管理 — 托盘图标 + 右键菜单
"""

from PIL import Image, ImageDraw
import pystray

on_open_triggered = None
on_capture_triggered = None
on_quit = None


def _create_tray_icon_image():
    """生成托盘图标（32x32 圆角方框 + 翻译符号）"""
    img = Image.new("RGBA", (32, 32), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角方形背景（靛蓝色）
    draw.rounded_rectangle([1, 1, 30, 30], radius=6, fill=(79, 70, 229))

    # 左侧小竖条（代表原文）
    draw.rounded_rectangle([7, 9, 11, 23], radius=2, fill=(255, 255, 255))
    # 右侧小竖条（代表译文）
    draw.rounded_rectangle([20, 9, 24, 23], radius=2, fill=(199, 210, 254))

    # 中间箭头（→）
    draw.polygon([
        (14, 16), (19, 14), (19, 18)  # 箭头 tip
    ], fill=(165, 180, 252))

    return img


def _on_tray_activate(icon, item):
    if item.text == "打开翻译窗口" and on_open_triggered:
        on_open_triggered()
    elif item.text == "框选翻译" and on_capture_triggered:
        on_capture_triggered()
    elif item.text == "退出":
        if on_quit:
            on_quit()
        icon.stop()


def start_tray():
    icon_img = _create_tray_icon_image()

    menu = pystray.Menu(
        pystray.MenuItem("打开翻译窗口", _on_tray_activate, default=True),
        pystray.MenuItem("框选翻译", _on_tray_activate),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _on_tray_activate),
    )

    tray = pystray.Icon(
        "screen_translator",
        icon_img,
        "屏幕翻译 (Shift+Win+Z)",
        menu,
    )

    print("[OK] 系统托盘已启动")
    tray.run()
    print("[OK] 程序已退出")
