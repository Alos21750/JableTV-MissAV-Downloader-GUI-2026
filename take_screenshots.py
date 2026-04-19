#!/usr/bin/env python
# coding: utf-8
"""Automated screenshot capture for the Material-Design GUI (gui_modern)."""

import ctypes
import os
import sys

# Force DPI-unaware so screenshots capture at 1:1 logical pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(0)
except Exception:
    pass

sys.path.insert(0, os.path.dirname(__file__))

from PIL import ImageGrab  # noqa: E402

import customtkinter as ctk  # noqa: E402
ctk.deactivate_automatic_dpi_awareness()
ctk.set_widget_scaling(1.0)
ctk.set_window_scaling(1.0)

from gui_modern import DownloadItem, ModernApp  # noqa: E402

SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), 'img')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def capture_window(win, filename):
    """Capture the app content area — maximized + topmost so nothing bleeds through."""
    filepath = os.path.join(SCREENSHOTS_DIR, filename)
    win.update_idletasks()
    win.attributes('-topmost', True)
    win.lift()
    win.focus_force()
    win.update()
    # Let the window fully repaint after tab switch
    import time
    time.sleep(0.3)
    win.update()

    x = win.winfo_rootx()
    y = win.winfo_rooty()
    w = win.winfo_width()
    h = win.winfo_height()

    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(filepath, optimize=True)
    pw, ph = img.size
    print(f'[screenshot] {filename}  {pw}x{ph}  ({os.path.getsize(filepath):,} B)')
    win.attributes('-topmost', False)


def populate_downloads(app: ModernApp):
    """Fill the download manager with realistic demo items."""
    demos = [
        ('https://jable.tv/videos/ssis-001/', '下載中',
         'SSIS-001 三上悠亞の極上テクニック', 67, '2.3 MB/s'),
        ('https://jable.tv/videos/ipx-486/', '下載中',
         'IPX-486 天然成分由来 美少女汁120%', 34, '1.8 MB/s'),
        ('https://jable.tv/videos/stars-325/', '下載中',
         'STARS-325 永野いち夏 完全覚醒', 89, '3.1 MB/s'),
        ('https://jable.tv/videos/mide-953/', '下載中',
         'MIDE-953 高橋しょう子が凄テクで', 12, '2.0 MB/s'),
        ('https://jable.tv/videos/pred-309/', '下載中',
         'PRED-309 篠田ゆうの絶頂4本番', 51, '1.5 MB/s'),
        ('https://missav.ai/dm132/ja/sone-001', '等待中',
         'SONE-001 新人NO.1 河北彩花', 0, ''),
        ('https://missav.ws/dm132/ja/midv-139', '等待中',
         'MIDV-139 田中ねねの豊満Jcup', 0, ''),
        ('https://jable.tv/videos/cawd-301/', '等待中',
         'CAWD-301 伊藤舞雪 最高の美女', 0, ''),
        ('https://jable.tv/videos/ssni-756/', '已下載',
         'SSNI-756 橋本ありなの最新作品', 100, ''),
        ('https://jable.tv/videos/jul-679/', '已下載',
         'JUL-679 Madonna専属 美人妻', 100, ''),
    ]
    for url, state, name, pct, speed in demos:
        app._dlmgr.add_item(url, name=name, state=state)
        item = app._dlmgr._items[url]   # direct access ok for demo data
        item.name = name
        item.state = state
        item.progress = pct
        item.speed = speed


def run():
    app = ModernApp(url='', dest='download')
    # True fullscreen — covers entire screen, no title bar, no other windows visible
    app.overrideredirect(True)
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    app.geometry(f'{screen_w}x{screen_h}+0+0')
    app.update_idletasks()

    step = [0]

    def next_step():
        s = step[0]
        step[0] += 1

        if s == 0:
            # Browse - JableTV
            app._tabs.set('瀏覽')
            try:
                app._site_var.set('JableTV')
                app._on_site_change('JableTV')
            except Exception as e:
                print(f'[WARN] site switch: {e}')
            app.after(7000, next_step)

        elif s == 1:
            capture_window(app, 'screenshot_browse_jable.png')
            app.after(800, next_step)

        elif s == 2:
            # Browse - MissAV
            try:
                app._site_var.set('MissAV')
                app._on_site_change('MissAV')
            except Exception as e:
                print(f'[WARN] site switch: {e}')
            app.after(7000, next_step)

        elif s == 3:
            capture_window(app, 'screenshot_browse_missav.png')
            app.after(800, next_step)

        elif s == 4:
            # Download tab
            app._tabs.set('下載')
            populate_downloads(app)
            app.after(1800, next_step)

        elif s == 5:
            capture_window(app, 'screenshot_download.png')
            app.after(800, next_step)

        elif s == 6:
            # Settings tab
            app._tabs.set('設定')
            app.after(1200, next_step)

        elif s == 7:
            capture_window(app, 'screenshot_settings.png')
            app.after(600, next_step)

        elif s == 8:
            print('\n=== All screenshots captured ===')
            app.after(1200, app.destroy)

    app.after(3000, next_step)
    app.mainloop()


if __name__ == '__main__':
    run()
