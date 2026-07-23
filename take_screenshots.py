#!/usr/bin/env python
# coding: utf-8
"""Capture the two current desktop UIs used by the GitHub READMEs.

The script keeps the user's saved preferences and download queue untouched. The
Modern screenshot uses a live JableTV browse page; the SmallTool screenshot is
an idle configuration screen with two example category selections.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import tempfile
import time

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

import config  # noqa: E402
import gui_modern  # noqa: E402
import jable_smalltool  # noqa: E402
from smalltool_categories import find_target, selection_key  # noqa: E402


SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), 'img')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def capture_window(win, filename):
    """Capture only the application window, with no desktop bleed-through."""
    filepath = os.path.join(SCREENSHOTS_DIR, filename)
    win.update_idletasks()
    win.attributes('-topmost', True)
    win.lift()
    win.focus_force()
    win.update()
    time.sleep(0.5)
    win.update()

    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(win.winfo_id(), ctypes.byref(rect))
    # A DPI-unaware Tk process reports logical coordinates while ImageGrab
    # consumes physical pixels. Derive the scale from the active desktop so
    # the capture includes the entire window on 125%/150% displays.
    desktop_width, desktop_height = ImageGrab.grab().size
    scale_x = desktop_width / win.winfo_screenwidth()
    scale_y = desktop_height / win.winfo_screenheight()
    image = ImageGrab.grab(bbox=(
        round(rect.left * scale_x),
        round(rect.top * scale_y),
        round(rect.right * scale_x),
        round(rect.bottom * scale_y),
    ))
    image.save(filepath, optimize=True)
    print(f'[screenshot] {filename} {image.width}x{image.height}')
    win.attributes('-topmost', False)


def prepare_window(app, width=1280, height=800):
    app.overrideredirect(True)
    app.geometry(f'{width}x{height}+0+0')
    app.update_idletasks()


def capture_modern():
    config.get_ui_lang = lambda: 'en'
    config.get_theme = lambda: 'dark'
    config.get_proxy_url = lambda: ''
    config.get_proxy_mode = lambda: 'direct'
    config.get_download_concurrency = lambda: 2
    gui_modern.CSV_PATH = os.path.join(
        tempfile.gettempdir(), 'jable_readme_empty_queue.csv')
    try:
        os.remove(gui_modern.CSV_PATH)
    except FileNotFoundError:
        pass

    app = gui_modern.ModernApp(url='', dest='download')
    prepare_window(app)
    app._select_tab('browse')
    app._site_var.set('JableTV')
    app._on_site_change('JableTV')

    def finish():
        capture_window(app, 'readme_modern.png')
        app._on_close()

    app.after(9000, finish)
    app.mainloop()


def capture_smalltool():
    config.get_ui_lang = lambda: 'zh'
    config.get_theme = lambda: 'dark'
    config.get_proxy_url = lambda: ''
    config.get_proxy_mode = lambda: 'direct'
    config.get_download_concurrency = lambda: 2
    jable_smalltool.load_config = lambda: {
        'output_folder': r'.\tmp',
        'baseline_date': jable_smalltool.DEFAULT_BASELINE_DATE,
        'resolution': 'highest',
        'version_preference': 'chinese-subtitle',
        'first_run_done': False,
        'selected_targets': [],
    }
    jable_smalltool.save_config = lambda _cfg: None

    app = jable_smalltool.SmallToolApp()
    prepare_window(app, width=1200, height=800)
    tab_name = 'MissAV  102'
    app._category_tabview.set(tab_name)
    for name in ('亂倫', 'NTR'):
        target = find_target('MissAV', legacy_name=name)
        if target:
            app._check_vars[selection_key('MissAV', target['id'])].set(True)
    app._sync_select_all_vars()
    capture_window(app, 'readme_smalltool.png')
    app._on_close()


def run():
    if len(sys.argv) == 1:
        for target in ('modern', 'smalltool'):
            subprocess.run(
                [sys.executable, os.path.abspath(__file__), target],
                check=True)
        print('README screenshots captured.')
        return
    if sys.argv[1] == 'modern':
        capture_modern()
        return
    if sys.argv[1] == 'smalltool':
        capture_smalltool()
        return
    raise SystemExit('usage: take_screenshots.py [modern|smalltool]')


if __name__ == '__main__':
    run()
