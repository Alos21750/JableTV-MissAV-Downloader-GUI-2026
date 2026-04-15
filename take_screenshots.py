#!/usr/bin/env python
# coding: utf-8
"""Automated screenshot capture for README documentation."""

import sys
import os
import ctypes
import ctypes.wintypes

# Enable DPI awareness BEFORE any Tk/GUI imports
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(__file__))

import tkinter as tk
from gui import MainWindow
from PIL import ImageGrab

SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), 'img')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def capture_tk_window(win, filename):
    """Capture the Tk window by its own HWND, not the foreground window."""
    filepath = os.path.join(SCREENSHOTS_DIR, filename)
    win.update_idletasks()
    win.lift()
    win.focus_force()
    win.update()

    # Get the Tk window's own HWND
    hwnd = ctypes.windll.user32.FindWindowW(None, win.title())
    if not hwnd:
        # Fallback: use wm_frame
        hwnd = int(win.wm_frame(), 16)

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                     ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    rect = RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))

    # Small inset to remove window shadow/border
    img = ImageGrab.grab(bbox=(rect.left + 1, rect.top + 1,
                               rect.right - 1, rect.bottom - 1))
    img.save(filepath, optimize=True)
    w, h = img.size
    sz = os.path.getsize(filepath)
    print(f'[screenshot] {filename}  {w}x{h}  ({sz:,} bytes)')


def populate_download_demo(win):
    """Fill the download queue with realistic demo entries."""
    tree = win._queue_tree
    demos = [
        ('https://jable.tv/videos/ssis-001/', '下載中', 'SSIS-001 三上悠亞の極上テクニック', '67%', '2.3 MB/s'),
        ('https://jable.tv/videos/ipx-486/',  '下載中', 'IPX-486 天然成分由来 美少女汁120%', '34%', '1.8 MB/s'),
        ('https://jable.tv/videos/stars-325/', '下載中', 'STARS-325 永野いち夏 完全覚醒', '89%', '3.1 MB/s'),
        ('https://jable.tv/videos/mide-953/',  '下載中', 'MIDE-953 高橋しょう子が凄テクで', '12%', '2.0 MB/s'),
        ('https://jable.tv/videos/pred-309/',  '下載中', 'PRED-309 篠田ゆうの絶頂4本番', '51%', '1.5 MB/s'),
        ('https://missav.ai/dm132/ja/sone-001','等待中', 'SONE-001 新人NO.1 河北彩花', '', ''),
        ('https://missav.ws/dm132/ja/midv-139','等待中', 'MIDV-139 田中ねねの豊満Jcup', '', ''),
        ('https://jable.tv/videos/cawd-301/',  '等待中', 'CAWD-301 伊藤舞雪 最高の美女', '', ''),
        ('https://jable.tv/videos/ssni-756/',  '已下載', 'SSNI-756 橋本ありなの最新作品', '100%', ''),
        ('https://jable.tv/videos/jul-679/',   '已下載', 'JUL-679 Madonna専属 美人妻', '100%', ''),
    ]
    for url, state, name, progress, speed in demos:
        iid = tree._iid(url)
        if not tree.exists(iid):
            tree.insert('', 'end', iid=iid,
                        values=(state, name, progress, speed, url),
                        tags=(state,))

    win._status_lbl.configure(text='下載中 5/10  |  等待中 3  |  已完成 2')
    win._console.write('✓ SSNI-756 橋本ありなの最新作品 下載完成\n')
    win._console.write('✓ JUL-679 Madonna専属 美人妻 下載完成\n')
    win._console.write('下載中: SSIS-001 三上悠亞の極上テクニック [67%] 2.3 MB/s\n')
    win._console.write('下載中: IPX-486 天然成分由来 美少女汁120% [34%] 1.8 MB/s\n')
    win._console.write('下載中: STARS-325 永野いち夏 完全覚醒 [89%] 3.1 MB/s\n')
    win._console.write('等待中: SONE-001 新人NO.1 河北彩花\n')
    win._console.write('等待中: MIDV-139 田中ねねの豊満Jcup\n')


def run():
    win = MainWindow(dest='download')
    win.state('zoomed')
    win.update_idletasks()

    step = [0]

    def next_step():
        s = step[0]
        step[0] += 1

        if s == 0:
            win._notebook.select(0)
            browse = win._browse
            browse._site_var.set('JableTV')
            browse._on_site_change(None)
            win.after(6000, next_step)

        elif s == 1:
            capture_tk_window(win, 'screenshot_browse_jable.png')
            win.after(1000, next_step)

        elif s == 2:
            browse = win._browse
            browse._site_var.set('MissAV')
            browse._on_site_change(None)
            win.after(6000, next_step)

        elif s == 3:
            capture_tk_window(win, 'screenshot_browse_missav.png')
            win.after(1000, next_step)

        elif s == 4:
            win._notebook.select(1)
            populate_download_demo(win)
            win.after(1500, next_step)

        elif s == 5:
            capture_tk_window(win, 'screenshot_download.png')
            win.after(500, next_step)

        elif s == 6:
            print('\n=== All screenshots captured ===')
            win.after(1500, win.destroy)

    win.after(3000, next_step)
    win.mainloop()


if __name__ == '__main__':
    run()
