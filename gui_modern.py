#!/usr/bin/env python
# coding: utf-8
"""Modern GUI for JableTV & MissAV Downloader by ALOS — CustomTkinter Material Design."""

import os
import sys
import re
import io
import csv
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
import requests
from PIL import Image

import M3U8Sites
from M3U8Sites.SiteJableTV import JableTVBrowser
from M3U8Sites.SiteMissAV import MissAVBrowser
from config import headers

# ── Design tokens ────────────────────────────────────────────────────
ACCENT = '#e94560'
ACCENT_HOVER = '#c73350'
ACCENT2 = '#7b61ff'
SUCCESS = '#4ade80'
WARNING = '#fbbf24'
ERROR_C = '#f87171'
BG_DARK = '#0d0d18'
BG_CARD = '#161630'
BG_INPUT = '#1c1c38'
BG_HEADER = '#101020'
BG_SECTION = '#131328'
TEXT_PRI = '#f0f0f8'
TEXT_SEC = '#a0a0c0'
TEXT_DIM = '#666688'
BORDER = '#2a2a48'

DEFAULT_CONCURRENT = 2
MAX_CONCURRENT = 10
CSV_PATH = os.path.join(os.getcwd(), 'JableTV.csv')

SITES = {
    'JableTV': {'browser': JableTVBrowser},
    'MissAV': {'browser': MissAVBrowser},
}


# ── Download Manager ────────────────────────────────────────────────
class DownloadItem:
    __slots__ = ('url', 'name', 'state', 'progress', 'speed')

    def __init__(self, url: str, name: str = '', state: str = ''):
        self.url = url
        self.name = name or url.rstrip('/').split('/')[-1]
        self.state = state
        self.progress = 0
        self.speed = ''


class DownloadManager:
    """Thread-safe download manager with configurable concurrency."""

    def __init__(self, on_update=None, max_concurrent: int = DEFAULT_CONCURRENT):
        self._on_update = on_update
        self._pending: list[tuple[str, str]] = []
        self._active: dict[str, object] = {}
        self._items: dict[str, DownloadItem] = {}
        # RLock: enqueue() and cancel_all() call _set_state() while holding
        # the lock — a plain Lock would deadlock the caller (often the main
        # GUI thread, freezing the app).
        self._lock = threading.RLock()
        self._max_concurrent = max_concurrent
        self._prep_sem = threading.Semaphore(1)

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @max_concurrent.setter
    def max_concurrent(self, value: int):
        self._max_concurrent = max(1, min(value, MAX_CONCURRENT))
        for _ in range(value):
            self._try_next()

    def add_item(self, url: str, name: str = '', state: str = ''):
        with self._lock:
            if url not in self._items:
                self._items[url] = DownloadItem(url, name, state)

    def get_items(self) -> list[DownloadItem]:
        with self._lock:
            return list(self._items.values())

    def remove_item(self, url: str):
        with self._lock:
            self._items.pop(url, None)
            self._pending = [(u, d) for u, d in self._pending if u != url]
            job = self._active.pop(url, None)
        if job and hasattr(job, 'cancel_download'):
            try:
                job.cancel_download()
            except Exception:
                pass

    def enqueue(self, url: str, dest: str):
        with self._lock:
            if url in self._active:
                return
            if any(u == url for u, _ in self._pending):
                return
            if len(self._active) < self._max_concurrent:
                self._active[url] = None
                threading.Thread(target=self._run, args=(url, dest),
                                 daemon=True).start()
            else:
                self._pending.append((url, dest))
                self._set_state(url, '等待中')

    def cancel_all(self):
        with self._lock:
            for u, _ in self._pending:
                self._set_state(u, '已取消')
            self._pending.clear()
            jobs = list(self._active.items())
        for url, job in jobs:
            if job and hasattr(job, 'cancel_download'):
                try:
                    job.cancel_download()
                except Exception:
                    pass
            self._set_state(url, '已取消')
        with self._lock:
            self._active.clear()

    def clear_all(self):
        self.cancel_all()
        with self._lock:
            self._items.clear()

    def _run(self, url: str, dest: str):
        self._set_state(url, '準備中')
        try:
            self._prep_sem.acquire()
            try:
                job = M3U8Sites.CreateSite(url, dest)
            finally:
                self._prep_sem.release()
            if not job or not job.is_url_vaildate():
                with self._lock:
                    self._active.pop(url, None)
                self._set_state(url, '網址錯誤')
                self._try_next()
                return
            with self._lock:
                self._active[url] = job
            name = job.target_name() or ''
            self._set_state(url, '下載中', name=name)
            job._progress_callback = lambda d, t, s: self._on_progress(url, d, t, s)
            job.start_download()
            with self._lock:
                self._active.pop(url, None)
            if job._cancel_job:
                self._set_state(url, '已取消')
            else:
                self._set_state(url, '已下載', progress=100)
        except Exception as exc:
            print(f'[下載失敗] {url}\n  {exc}', flush=True)
            with self._lock:
                self._active.pop(url, None)
            self._set_state(url, '未完成')
        self._try_next()

    def _try_next(self):
        with self._lock:
            if not self._pending or len(self._active) >= self._max_concurrent:
                return
            url, dest = self._pending.pop(0)
            self._active[url] = None
        threading.Thread(target=self._run, args=(url, dest), daemon=True).start()

    def _set_state(self, url: str, state: str, name: str = '', progress: int = -1):
        with self._lock:
            item = self._items.get(url)
            if item:
                item.state = state
                if name:
                    item.name = name
                if progress >= 0:
                    item.progress = progress
                if state != '下載中':
                    item.speed = ''

    def _on_progress(self, url: str, done: int, total: int, speed_bps: float):
        if total <= 0:
            return
        pct = int(done * 100 / total)
        spd = (f'{speed_bps / 1024:.0f} KB/s' if speed_bps < 1024 * 1024
               else f'{speed_bps / 1024 / 1024:.1f} MB/s')
        with self._lock:
            item = self._items.get(url)
            if item:
                item.progress = pct
                item.speed = spd

    def save_csv(self, path: str):
        with self._lock:
            items = list(self._items.values())
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['狀態', '名稱', '進度', '速度', '網址'])
            for item in items:
                w.writerow([item.state, item.name, f'{item.progress}%',
                            item.speed, item.url])

    def load_csv(self, path: str):
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                url = row.get('網址', '')
                if url:
                    self.add_item(url, row.get('名稱', ''), row.get('狀態', ''))

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)


# ── Browse helper ────────────────────────────────────────────────────
def fetch_page_data(browser_cls, url: str) -> dict:
    """Fetch video list from a category/search URL. Returns dict with videos list."""
    try:
        videos = browser_cls.fetch_page(url)
        return {'videos': videos}
    except Exception as e:
        print(f'[瀏覽錯誤] {e}')
        return {'videos': []}


# ── Thumbnail loader ────────────────────────────────────────────────
_thumb_session: Optional[requests.Session] = None
_thumb_lock = threading.Lock()
_thumb_cache: dict = {}   # url -> PIL.Image (raw, not CTkImage; Tk root needed)
_THUMB_SIZE = (260, 146)  # 16:9 at 260px wide


def _get_thumb_session() -> requests.Session:
    global _thumb_session
    if _thumb_session is None:
        with _thumb_lock:
            if _thumb_session is None:
                s = requests.Session()
                a = requests.adapters.HTTPAdapter(pool_connections=8,
                                                  pool_maxsize=32)
                s.mount('http://', a)
                s.mount('https://', a)
                _thumb_session = s
    return _thumb_session


def _fetch_thumbnail(url: str) -> Optional[Image.Image]:
    """Download and decode a thumbnail; cached per-URL."""
    if not url:
        return None
    cached = _thumb_cache.get(url)
    if cached is not None:
        return cached
    try:
        r = _get_thumb_session().get(url, headers=headers, timeout=12)
        if r.status_code != 200:
            return None
        img = Image.open(io.BytesIO(r.content)).convert('RGB')
        img.thumbnail(_THUMB_SIZE, Image.LANCZOS)
        _thumb_cache[url] = img
        # Limit cache growth
        if len(_thumb_cache) > 200:
            # Drop oldest 40 entries
            for k in list(_thumb_cache.keys())[:40]:
                _thumb_cache.pop(k, None)
        return img
    except Exception:
        return None


# ── Main App ─────────────────────────────────────────────────────────
class ModernApp(ctk.CTk):
    def __init__(self, url: str = '', dest: str = 'download'):
        super().__init__()

        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('dark-blue')

        self.title('JableTV & MissAV Downloader — by ALOS')
        self.geometry('1280x800')
        self.minsize(1000, 650)
        self.configure(fg_color=BG_DARK)

        self._dest = dest
        self._url_input = url
        self._is_closing = False

        # Browse state
        self._site_key = 'JableTV'
        self._categories: list[dict] = []
        self._current_base_url = ''
        self._page = 1
        self._has_next = True
        self._videos: list[dict] = []
        self._selected_urls: set = set()
        self._sidebar_expanded: dict[str, bool] = {}
        self._grid_gen: int = 0  # bumps on each page refresh so stale thumbs are dropped
        self._card_widgets: dict = {}  # url -> {card, sel_btn}
        self._dl_rows: dict = {}   # url -> {row, state_lbl, name_lbl, pb, pct, spd, remove}
        self._dl_empty_lbl = None

        # Download manager
        self._dlmgr = DownloadManager(max_concurrent=DEFAULT_CONCURRENT)
        self._dlmgr.load_csv(CSV_PATH)

        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        # Start periodic refresh for downloads
        self._refresh_downloads()
        # Start clipboard monitor (main-thread safe)
        self._clp_text = ''
        self._clipboard_poll()

        # Load initial categories in background
        threading.Thread(target=self._load_categories, daemon=True).start()

    # ── Build UI ─────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=48, fg_color=BG_HEADER, corner_radius=0)
        header.pack(fill='x')
        header.pack_propagate(False)
        ctk.CTkLabel(header, text='JableTV & MissAV Downloader',
                     font=('Microsoft YaHei', 16, 'bold'),
                     text_color=ACCENT).pack(side='left', padx=16)
        ctk.CTkLabel(header, text='by ALOS  •  v2.0 Material',
                     font=('Microsoft YaHei', 11),
                     text_color=TEXT_DIM).pack(side='right', padx=16)

        # Tabview
        self._tabs = ctk.CTkTabview(self, fg_color=BG_DARK,
                                     segmented_button_fg_color=BG_HEADER,
                                     segmented_button_selected_color=ACCENT,
                                     segmented_button_unselected_color=BG_CARD,
                                     corner_radius=0)
        self._tabs.pack(fill='both', expand=True, padx=0, pady=0)
        self._tabs.add('瀏覽')
        self._tabs.add('下載')
        self._tabs.add('設定')

        self._build_browse_tab()
        self._build_download_tab()
        self._build_settings_tab()

        # Status bar
        status_bar = ctk.CTkFrame(self, height=28, fg_color=BG_HEADER, corner_radius=0)
        status_bar.pack(fill='x')
        status_bar.pack_propagate(False)
        self._status_lbl = ctk.CTkLabel(status_bar, text='就緒',
                                         font=('Consolas', 11),
                                         text_color=TEXT_SEC)
        self._status_lbl.pack(side='left', padx=12)

    # ── Browse Tab ───────────────────────────────────────────────────
    def _build_browse_tab(self):
        tab = self._tabs.tab('瀏覽')

        # Top bar
        top = ctk.CTkFrame(tab, fg_color=BG_SECTION, corner_radius=0, height=50)
        top.pack(fill='x')
        top.pack_propagate(False)

        # Site selector
        self._site_var = ctk.StringVar(value='JableTV')
        ctk.CTkLabel(top, text='站點:', text_color=TEXT_SEC,
                     font=('Microsoft YaHei', 11)).pack(side='left', padx=(12, 4))
        self._site_menu = ctk.CTkOptionMenu(
            top, values=list(SITES.keys()), variable=self._site_var,
            command=self._on_site_change, width=100,
            fg_color=BG_INPUT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER)
        self._site_menu.pack(side='left', padx=4)

        # Category selector
        ctk.CTkLabel(top, text='分類:', text_color=TEXT_SEC,
                     font=('Microsoft YaHei', 11)).pack(side='left', padx=(12, 4))
        self._cat_var = ctk.StringVar(value='載入中...')
        self._cat_menu = ctk.CTkOptionMenu(
            top, values=['載入中...'], variable=self._cat_var,
            command=self._on_cat_change, width=160,
            fg_color=BG_INPUT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER)
        self._cat_menu.pack(side='left', padx=4)

        # Search
        self._search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(top, textvariable=self._search_var,
                                     placeholder_text='搜尋影片...',
                                     width=200, fg_color=BG_INPUT,
                                     border_color=BORDER, text_color=TEXT_PRI)
        search_entry.pack(side='left', padx=(12, 4))
        search_entry.bind('<Return>', lambda e: self._on_search())
        ctk.CTkButton(top, text='搜尋', command=self._on_search,
                      width=60, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER).pack(side='left', padx=4)

        # Selection controls
        self._sel_lbl = ctk.CTkLabel(top, text='', text_color=ACCENT,
                                      font=('Microsoft YaHei', 11, 'bold'))
        self._sel_lbl.pack(side='right', padx=8)
        ctk.CTkButton(top, text='下載選中', command=self._download_selected,
                      width=80, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER).pack(side='right', padx=4)
        ctk.CTkButton(top, text='加入清單', command=self._add_selected_to_queue,
                      width=80, fg_color=BG_CARD,
                      hover_color='#2a2a4a',
                      text_color=TEXT_PRI).pack(side='right', padx=4)

        # Content area: sidebar + grid
        content = ctk.CTkFrame(tab, fg_color=BG_DARK, corner_radius=0)
        content.pack(fill='both', expand=True)

        # Sidebar
        self._sidebar = ctk.CTkScrollableFrame(
            content, width=130, fg_color='#0a0a16',
            corner_radius=0, scrollbar_button_color=BORDER)
        self._sidebar.pack(side='left', fill='y')

        # Video grid area
        grid_area = ctk.CTkFrame(content, fg_color=BG_DARK, corner_radius=0)
        grid_area.pack(side='left', fill='both', expand=True)

        self._grid_scroll = ctk.CTkScrollableFrame(
            grid_area, fg_color=BG_DARK, corner_radius=0)
        self._grid_scroll.pack(fill='both', expand=True)

        # Navigation bar
        nav = ctk.CTkFrame(tab, fg_color=BG_HEADER, corner_radius=0, height=40)
        nav.pack(fill='x')
        nav.pack_propagate(False)
        ctk.CTkButton(nav, text='« 首頁', width=60, fg_color=BG_CARD,
                      hover_color='#2a2a4a', text_color=TEXT_PRI,
                      command=lambda: self._goto_page(1)).pack(side='left', padx=4, pady=4)
        ctk.CTkButton(nav, text='‹ 上一頁', width=70, fg_color=BG_CARD,
                      hover_color='#2a2a4a', text_color=TEXT_PRI,
                      command=lambda: self._goto_page(self._page - 1)
                      ).pack(side='left', padx=4, pady=4)
        self._page_lbl = ctk.CTkLabel(nav, text='第 1 頁', text_color=TEXT_PRI,
                                       font=('Microsoft YaHei', 12, 'bold'),
                                       width=80)
        self._page_lbl.pack(side='left', padx=8)
        ctk.CTkButton(nav, text='下一頁 ›', width=70, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=lambda: self._goto_page(self._page + 1)
                      ).pack(side='left', padx=4, pady=4)

        self._rebuild_sidebar()

    # ── Download Tab ─────────────────────────────────────────────────
    def _build_download_tab(self):
        tab = self._tabs.tab('下載')

        # Input section
        input_frame = ctk.CTkFrame(tab, fg_color=BG_SECTION, corner_radius=0)
        input_frame.pack(fill='x', padx=0, pady=0)

        row1 = ctk.CTkFrame(input_frame, fg_color='transparent')
        row1.pack(fill='x', padx=12, pady=(8, 4))
        ctk.CTkLabel(row1, text='存放位置', text_color=TEXT_SEC, width=70,
                     font=('Microsoft YaHei', 11)).pack(side='left')
        self._dest_var = ctk.StringVar(value=self._dest)
        ctk.CTkEntry(row1, textvariable=self._dest_var,
                     fg_color=BG_INPUT, border_color=BORDER,
                     text_color=TEXT_PRI).pack(side='left', fill='x',
                                               expand=True, padx=8)
        ctk.CTkButton(row1, text='瀏覽', width=60, fg_color=BG_CARD,
                      hover_color='#2a2a4a', text_color=TEXT_PRI,
                      command=self._pick_dest).pack(side='left')
        ctk.CTkButton(row1, text='開啟', width=50, fg_color=BG_CARD,
                      hover_color='#2a2a4a', text_color=TEXT_PRI,
                      command=self._open_dest_folder).pack(side='left', padx=(4, 0))

        row2 = ctk.CTkFrame(input_frame, fg_color='transparent')
        row2.pack(fill='x', padx=12, pady=(0, 8))
        ctk.CTkLabel(row2, text='下載網址', text_color=TEXT_SEC, width=70,
                     font=('Microsoft YaHei', 11)).pack(side='left')
        self._dl_url_var = ctk.StringVar(value=self._url_input)
        ctk.CTkEntry(row2, textvariable=self._dl_url_var,
                     fg_color=BG_INPUT, border_color=BORDER,
                     text_color=TEXT_PRI).pack(side='left', fill='x',
                                               expand=True, padx=8)

        # Action bar
        bar = ctk.CTkFrame(tab, fg_color=BG_HEADER, corner_radius=0, height=44)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        ctk.CTkButton(bar, text='▶ 下載', width=80, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._download_url).pack(side='left', padx=6, pady=6)
        ctk.CTkButton(bar, text='▶▶ 全部下載', width=100, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._download_all).pack(side='left', padx=4)

        ctk.CTkButton(bar, text='清空', width=60, fg_color='#3a1a20',
                      hover_color='#2a1215', text_color=ERROR_C,
                      command=self._clear_queue).pack(side='right', padx=6, pady=6)
        ctk.CTkButton(bar, text='全部取消', width=80, fg_color='#3a1a20',
                      hover_color='#2a1215', text_color=ERROR_C,
                      command=self._cancel_all).pack(side='right', padx=4)

        # Speed limiter
        ctk.CTkLabel(bar, text='速度:', text_color=TEXT_SEC,
                     font=('Microsoft YaHei', 10)).pack(side='right', padx=(0, 4))
        self._speed_var = ctk.StringVar(value='無限制')
        ctk.CTkOptionMenu(bar, values=['無限制', '1 MB/s', '2 MB/s', '5 MB/s',
                                        '10 MB/s', '15 MB/s'],
                          variable=self._speed_var,
                          command=self._on_speed_change, width=100,
                          fg_color=BG_INPUT, button_color=ACCENT,
                          button_hover_color=ACCENT_HOVER
                          ).pack(side='right', padx=4, pady=6)

        # Download list
        self._dl_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=BG_DARK, corner_radius=0)
        self._dl_scroll.pack(fill='both', expand=True)

    # ── Settings Tab ─────────────────────────────────────────────────
    def _build_settings_tab(self):
        tab = self._tabs.tab('設定')

        outer = ctk.CTkFrame(tab, fg_color=BG_DARK, corner_radius=0)
        outer.pack(fill='both', expand=True, padx=40, pady=20)

        ctk.CTkLabel(outer, text='設定', font=('Microsoft YaHei', 18, 'bold'),
                     text_color=TEXT_PRI).pack(anchor='w', pady=(0, 16))

        # Download settings
        grp = ctk.CTkFrame(outer, fg_color=BG_SECTION, corner_radius=8)
        grp.pack(fill='x', pady=(0, 16))

        ctk.CTkLabel(grp, text='下載設定', font=('Microsoft YaHei', 12, 'bold'),
                     text_color=TEXT_SEC).pack(anchor='w', padx=16, pady=(12, 8))

        # Save location
        row_dest = ctk.CTkFrame(grp, fg_color='transparent')
        row_dest.pack(fill='x', padx=16, pady=4)
        ctk.CTkLabel(row_dest, text='存放位置', text_color=TEXT_SEC,
                     width=80).pack(side='left')
        ctk.CTkEntry(row_dest, textvariable=self._dest_var,
                     fg_color=BG_INPUT, border_color=BORDER,
                     text_color=TEXT_PRI).pack(side='left', fill='x',
                                               expand=True, padx=8)
        ctk.CTkButton(row_dest, text='瀏覽', width=60, fg_color=BG_CARD,
                      hover_color='#2a2a4a', text_color=TEXT_PRI,
                      command=self._pick_dest).pack(side='left')

        # Speed limit
        row_speed = ctk.CTkFrame(grp, fg_color='transparent')
        row_speed.pack(fill='x', padx=16, pady=4)
        ctk.CTkLabel(row_speed, text='速度限制', text_color=TEXT_SEC,
                     width=80).pack(side='left')
        ctk.CTkOptionMenu(row_speed, values=['無限制', '1 MB/s', '2 MB/s',
                                              '5 MB/s', '10 MB/s', '15 MB/s'],
                          variable=self._speed_var,
                          command=self._on_speed_change, width=120,
                          fg_color=BG_INPUT, button_color=ACCENT,
                          button_hover_color=ACCENT_HOVER).pack(side='left', padx=8)

        # Concurrent downloads
        row_conc = ctk.CTkFrame(grp, fg_color='transparent')
        row_conc.pack(fill='x', padx=16, pady=(4, 12))
        ctk.CTkLabel(row_conc, text='同時下載數', text_color=TEXT_SEC,
                     width=80).pack(side='left')
        self._conc_var = ctk.StringVar(value=str(DEFAULT_CONCURRENT))
        ctk.CTkOptionMenu(row_conc,
                          values=[str(i) for i in range(1, MAX_CONCURRENT + 1)],
                          variable=self._conc_var,
                          command=self._on_conc_change, width=80,
                          fg_color=BG_INPUT, button_color=ACCENT,
                          button_hover_color=ACCENT_HOVER).pack(side='left', padx=8)
        ctk.CTkLabel(row_conc, text=f'(最多 {MAX_CONCURRENT})',
                     text_color=TEXT_DIM).pack(side='left')

        # About
        about = ctk.CTkFrame(outer, fg_color=BG_SECTION, corner_radius=8)
        about.pack(fill='x', pady=(0, 16))
        ctk.CTkLabel(about, text='關於', font=('Microsoft YaHei', 12, 'bold'),
                     text_color=TEXT_SEC).pack(anchor='w', padx=16, pady=(12, 4))
        ctk.CTkLabel(about, text='JableTV & MissAV Downloader',
                     text_color=TEXT_PRI,
                     font=('Microsoft YaHei', 13)).pack(anchor='w', padx=16)
        ctk.CTkLabel(about, text='by ALOS (Alos21750)',
                     text_color=ACCENT,
                     font=('Microsoft YaHei', 11)).pack(anchor='w', padx=16, pady=2)
        ctk.CTkLabel(about, text='v2.0.0 Material UI  •  僅供學習與研究用途',
                     text_color=TEXT_SEC,
                     font=('Microsoft YaHei', 10)).pack(anchor='w', padx=16, pady=(0, 12))

    # ── Browse logic ─────────────────────────────────────────────────
    def _load_categories(self):
        browser = SITES[self._site_key]['browser']
        try:
            cats = browser.fetch_categories()
        except Exception:
            cats = []
        self._categories = cats
        if cats:
            self._current_base_url = cats[0]['url']
            names = [c['name'] for c in cats]
            self.after(0, lambda: self._update_cat_menu(names))
            self.after(0, self._load_page)

    def _update_cat_menu(self, names: list[str]):
        self._cat_menu.configure(values=names)
        if names:
            self._cat_var.set(names[0])

    def _load_page(self):
        browser = SITES[self._site_key]['browser']
        base = self._current_base_url
        if self._site_key == 'JableTV':
            if '?' in base:
                url = f'{base}&from_videos={self._page}'
            else:
                url = f'{base.rstrip("/")}/?from={self._page}'
        else:
            url = MissAVBrowser.page_url(base, self._page)

        def _fetch():
            data = fetch_page_data(browser, url)
            self._videos = data.get('videos', [])
            self.after(0, self._refresh_grid)
            self.after(0, lambda: self._page_lbl.configure(
                text=f'第 {self._page} 頁'))

        threading.Thread(target=_fetch, daemon=True).start()

    def _refresh_grid(self):
        for w in self._grid_scroll.winfo_children():
            w.destroy()
        self._card_widgets = {}  # url -> {card, sel_btn}

        if not self._videos:
            ctk.CTkLabel(self._grid_scroll, text='沒有找到影片',
                         text_color=TEXT_DIM,
                         font=('Microsoft YaHei', 14)).pack(pady=40)
            return

        # Bump generation — any in-flight thumbnail loads from older
        # pages will find a mismatch and silently drop their result.
        self._grid_gen += 1
        gen = self._grid_gen

        # Create grid of cards, 4 per row
        row_frame = None
        for i, v in enumerate(self._videos):
            if i % 4 == 0:
                row_frame = ctk.CTkFrame(self._grid_scroll, fg_color='transparent')
                row_frame.pack(fill='x', padx=8, pady=4)

            url = v.get('url', '')
            title = v.get('title', '')
            dur = v.get('duration', '')
            thumb_url = v.get('thumbnail', '')
            is_sel = url in self._selected_urls

            card = ctk.CTkFrame(row_frame, fg_color=BG_CARD, corner_radius=8,
                                border_width=2,
                                border_color=ACCENT if is_sel else BORDER)
            card.pack(side='left', padx=4, pady=4, fill='x', expand=True)

            # Thumbnail placeholder (fixed 16:9 area)
            thumb_holder = ctk.CTkFrame(card, fg_color='#0a0a18',
                                         height=_THUMB_SIZE[1], corner_radius=6)
            thumb_holder.pack(fill='x', padx=6, pady=(6, 0))
            thumb_holder.pack_propagate(False)
            thumb_lbl = ctk.CTkLabel(thumb_holder, text='載入中...',
                                      text_color=TEXT_DIM,
                                      fg_color='transparent',
                                      font=('Microsoft YaHei', 10))
            thumb_lbl.pack(expand=True)

            # Duration badge over thumbnail (bottom-right)
            if dur:
                dur_lbl = ctk.CTkLabel(thumb_holder, text=dur,
                                        text_color='#ffffff',
                                        fg_color='#000000',
                                        corner_radius=3,
                                        font=('Consolas', 9, 'bold'))
                dur_lbl.place(relx=1.0, rely=1.0, anchor='se', x=-4, y=-4)

            # Title
            title_text = title[:60] + '…' if len(title) > 60 else title
            ctk.CTkLabel(card, text=title_text, text_color=TEXT_PRI,
                         font=('Microsoft YaHei', 10),
                         wraplength=240, justify='left').pack(
                padx=8, pady=(6, 2), anchor='w')

            # Bottom row: select button only (duration moved to thumbnail)
            bottom = ctk.CTkFrame(card, fg_color='transparent')
            bottom.pack(fill='x', padx=8, pady=(0, 8))

            sel_text = '✓ 已選' if is_sel else '選取'
            sel_btn = ctk.CTkButton(
                bottom, text=sel_text, width=60, height=24,
                fg_color=ACCENT if is_sel else BG_INPUT,
                hover_color=ACCENT_HOVER,
                font=('Microsoft YaHei', 9),
                command=lambda u=url: self._toggle_select(u)
            )
            sel_btn.pack(side='right')

            # Store widget refs for in-place selection updates
            self._card_widgets[url] = {'card': card, 'sel_btn': sel_btn}

            # Make the entire card clickable for selection
            def _bind_click(widget, video_url=url):
                widget.bind('<Button-1>', lambda e, u=video_url: self._toggle_select(u))
                # Cursor change to indicate clickability
                widget.configure(cursor='hand2')
            _bind_click(card)
            _bind_click(thumb_holder)
            _bind_click(thumb_lbl)

            # Kick off background thumbnail load
            if thumb_url:
                self._load_thumb_async(thumb_url, thumb_lbl, gen)
            else:
                thumb_lbl.configure(text='(無縮圖)')

    def _load_thumb_async(self, thumb_url: str, label: ctk.CTkLabel, gen: int):
        """Fetch thumbnail in a background thread; marshal result back to the
        main thread via .after() so Tk widget updates stay thread-safe.
        The gen counter prevents stale thumbs from polluting a newer page."""
        def _worker():
            img = _fetch_thumbnail(thumb_url)
            if img is None:
                return
            # Only apply if this label is still part of the current page.
            def _apply():
                if self._is_closing or gen != self._grid_gen:
                    return
                try:
                    if not label.winfo_exists():
                        return
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                            size=img.size)
                    label.configure(image=ctk_img, text='')
                    # Keep a reference on the widget so GC doesn't reclaim it
                    label._ctk_img_ref = ctk_img
                except Exception:
                    pass
            self.after(0, _apply)
        threading.Thread(target=_worker, daemon=True).start()

    def _toggle_select(self, url: str):
        if url in self._selected_urls:
            self._selected_urls.discard(url)
        else:
            self._selected_urls.add(url)
        # Update the specific card in-place (no full grid rebuild)
        w = self._card_widgets.get(url)
        if w:
            is_sel = url in self._selected_urls
            try:
                w['card'].configure(border_color=ACCENT if is_sel else BORDER)
                w['sel_btn'].configure(
                    text='✓ 已選' if is_sel else '選取',
                    fg_color=ACCENT if is_sel else BG_INPUT)
            except Exception:
                pass
        n = len(self._selected_urls)
        self._sel_lbl.configure(text=f'已選 {n} 部' if n else '')

    def _goto_page(self, p: int):
        if p < 1:
            return
        self._page = p
        self._load_page()

    def _on_site_change(self, val):
        self._site_key = val
        self._categories.clear()
        self._selected_urls.clear()
        self._sel_lbl.configure(text='')
        self._rebuild_sidebar()
        threading.Thread(target=self._load_categories, daemon=True).start()

    def _on_cat_change(self, val):
        idx = next((i for i, c in enumerate(self._categories)
                    if c['name'] == val), -1)
        if idx < 0:
            return
        self._current_base_url = self._categories[idx]['url']
        self._page = 1
        self._has_next = True
        self._selected_urls.clear()
        self._sel_lbl.configure(text='')
        self._load_page()

    def _on_search(self):
        q = self._search_var.get().strip()
        if not q:
            return
        if self._site_key == 'JableTV':
            self._current_base_url = f'https://jable.tv/search/?q={q}'
        else:
            self._current_base_url = f'https://missav.ai/dm265/cn/search?query={q}'
        self._page = 1
        self._has_next = True
        self._selected_urls.clear()
        self._sel_lbl.configure(text='')
        self._load_page()

    def _on_tag_click(self, url: str, name: str):
        self._current_base_url = url
        self._page = 1
        self._has_next = True
        self._selected_urls.clear()
        self._sel_lbl.configure(text='')
        self._cat_var.set(f'🏷 {name}')
        self._load_page()

    # ── Sidebar ──────────────────────────────────────────────────────
    def _rebuild_sidebar(self):
        for w in self._sidebar.winfo_children():
            w.destroy()

        ctk.CTkLabel(self._sidebar, text='標籤選片',
                     text_color=ACCENT,
                     font=('Microsoft YaHei', 12, 'bold')).pack(
            anchor='w', padx=8, pady=(8, 4))

        if self._site_key != 'JableTV':
            ctk.CTkLabel(self._sidebar, text='僅 JableTV\n支援標籤',
                         text_color=TEXT_DIM,
                         font=('Microsoft YaHei', 10)).pack(pady=20)
            return

        tags = JableTVBrowser.SIDEBAR_TAGS
        for group_name, tag_list in tags.items():
            expanded = self._sidebar_expanded.get(group_name, False)

            # Group header button
            arrow = '▾' if expanded else '▸'
            hdr = ctk.CTkButton(
                self._sidebar,
                text=f'{arrow} {group_name} ({len(tag_list)})',
                fg_color='#0e0e20', hover_color='#141430',
                text_color=TEXT_SEC, anchor='w',
                font=('Microsoft YaHei', 10, 'bold'),
                height=28, corner_radius=0,
                command=lambda g=group_name: self._toggle_group(g))
            hdr.pack(fill='x', padx=0, pady=0)

            if expanded:
                for name, slug in tag_list:
                    tag_url = JableTVBrowser.tag_url(slug)
                    btn = ctk.CTkButton(
                        self._sidebar, text=name,
                        fg_color='transparent', hover_color='#1a1a30',
                        text_color=TEXT_SEC, anchor='w',
                        font=('Microsoft YaHei', 10),
                        height=24, corner_radius=0,
                        command=lambda u=tag_url, n=name: self._on_tag_click(u, n))
                    btn.pack(fill='x', padx=(12, 0), pady=0)

    def _toggle_group(self, group: str):
        self._sidebar_expanded[group] = not self._sidebar_expanded.get(group, False)
        self._rebuild_sidebar()

    # ── Download actions ─────────────────────────────────────────────
    def _add_selected_to_queue(self):
        for url in list(self._selected_urls):
            if M3U8Sites.VaildateUrl(url):
                self._dlmgr.add_item(url, state='等待中')
        n = len(self._selected_urls)
        self._selected_urls.clear()
        self._sel_lbl.configure(text='')
        self._refresh_grid()
        print(f'已加入 {n} 部到清單')

    def _download_selected(self):
        dest = self._dest_var.get() or 'download'
        for url in list(self._selected_urls):
            if M3U8Sites.VaildateUrl(url):
                self._dlmgr.add_item(url, state='等待中')
                self._dlmgr.enqueue(url, dest)
        n = len(self._selected_urls)
        self._selected_urls.clear()
        self._sel_lbl.configure(text='')
        self._refresh_grid()
        print(f'{n} 部開始下載')

    def _download_url(self):
        url = self._dl_url_var.get().strip()
        if not url:
            return
        if not M3U8Sites.VaildateUrl(url):
            print(f'不支援的網址: {url}')
            return
        dest = self._dest_var.get() or 'download'
        self._dlmgr.add_item(url, state='等待中')
        self._dlmgr.enqueue(url, dest)

    def _download_all(self):
        dest = self._dest_var.get() or 'download'
        count = 0
        for item in self._dlmgr.get_items():
            # Skip items that are already active or completed; queued ('等待中')
            # items still need enqueue() to (re)start them.
            if item.state in ('已下載', '下載中', '準備中'):
                continue
            self._dlmgr.enqueue(item.url, dest)
            count += 1
        if count:
            print(f'已加入 {count} 個下載任務')

    def _cancel_all(self):
        self._dlmgr.cancel_all()

    def _clear_queue(self):
        self._dlmgr.clear_all()

    def _on_speed_change(self, val):
        from M3U8Sites.M3U8Crawler import speed_limiter
        if val == '無限制':
            speed_limiter.set_limit(0)
        else:
            mbps = float(val.split()[0])
            speed_limiter.set_limit(mbps)

    def _on_conc_change(self, val):
        self._dlmgr.max_concurrent = int(val)

    def _pick_dest(self):
        d = filedialog.askdirectory()
        if d:
            self._dest_var.set(d)

    def _open_dest_folder(self):
        import subprocess, platform
        dest = self._dest_var.get() or 'download'
        folder = os.path.abspath(dest)
        os.makedirs(folder, exist_ok=True)
        system = platform.system()
        if system == 'Windows':
            os.startfile(folder)
        elif system == 'Darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])

    # ── Download list refresh (incremental — no destroy/rebuild storm) ──
    _STATE_COLORS = {
        '下載中': ACCENT, '準備中': ACCENT2, '等待中': WARNING,
        '已下載': SUCCESS, '未完成': WARNING, '已取消': TEXT_DIM,
        '網址錯誤': ERROR_C,
    }

    def _refresh_downloads(self):
        if self._is_closing:
            return

        items = self._dlmgr.get_items()
        current_urls = {i.url for i in items}

        # Remove rows for items no longer present
        for url in list(self._dl_rows.keys()):
            if url not in current_urls:
                widgets = self._dl_rows.pop(url)
                try:
                    widgets['row'].destroy()
                except Exception:
                    pass

        # Toggle empty placeholder
        if not items:
            if self._dl_empty_lbl is None:
                self._dl_empty_lbl = ctk.CTkLabel(
                    self._dl_scroll, text='下載清單是空的',
                    text_color=TEXT_DIM,
                    font=('Microsoft YaHei', 13))
                self._dl_empty_lbl.pack(pady=40)
        else:
            if self._dl_empty_lbl is not None:
                try:
                    self._dl_empty_lbl.destroy()
                except Exception:
                    pass
                self._dl_empty_lbl = None

            # Create or update each row
            for item in items:
                if item.url in self._dl_rows:
                    self._update_dl_row(self._dl_rows[item.url], item)
                else:
                    self._dl_rows[item.url] = self._build_dl_row(item)

        # Update status bar
        a = self._dlmgr.active_count
        p = self._dlmgr.pending_count
        parts = []
        if a:
            parts.append(f'下載中 {a}/{self._dlmgr.max_concurrent}')
        if p:
            parts.append(f'等待中 {p}')
        done = sum(1 for i in items if i.state == '已下載')
        if done:
            parts.append(f'已完成 {done}')
        self._status_lbl.configure(text='  |  '.join(parts) if parts else '就緒')

        self.after(1000, self._refresh_downloads)

    def _build_dl_row(self, item: DownloadItem) -> dict:
        """Build one download row once; return widget handles for in-place updates."""
        color = self._STATE_COLORS.get(item.state, TEXT_SEC)

        row = ctk.CTkFrame(self._dl_scroll, fg_color=BG_CARD, corner_radius=4,
                           height=40)
        row.pack(fill='x', padx=4, pady=2)
        row.pack_propagate(False)

        state_lbl = ctk.CTkLabel(row, text=item.state or '—', text_color=color,
                                 font=('Microsoft YaHei', 10, 'bold'),
                                 width=60)
        state_lbl.pack(side='left', padx=8)

        name_lbl = ctk.CTkLabel(row, text=item.name or item.url,
                                text_color=TEXT_PRI,
                                font=('Microsoft YaHei', 10),
                                anchor='w')
        name_lbl.pack(side='left', fill='x', expand=True, padx=4)

        # Progress widgets (always present; hidden when not downloading)
        pb = ctk.CTkProgressBar(row, width=120, height=12,
                                fg_color='#1a1a2e',
                                progress_color=ACCENT)
        pb.set(max(0.0, min(1.0, item.progress / 100)))
        pct_lbl = ctk.CTkLabel(row, text='', text_color=TEXT_SEC,
                               font=('Consolas', 9), width=40)
        spd_lbl = ctk.CTkLabel(row, text='', text_color=TEXT_SEC,
                               font=('Consolas', 9), width=80)

        # Remove button
        remove_btn = ctk.CTkButton(
            row, text='✕', width=28, height=28,
            fg_color='transparent', hover_color='#3a1a20',
            text_color=TEXT_DIM, font=('Consolas', 12),
            command=lambda u=item.url: self._dlmgr.remove_item(u))
        remove_btn.pack(side='right', padx=4)

        widgets = {
            'row': row, 'state_lbl': state_lbl, 'name_lbl': name_lbl,
            'pb': pb, 'pct_lbl': pct_lbl, 'spd_lbl': spd_lbl,
            'pb_visible': False, 'pct_visible': False, 'spd_visible': False,
            'last_state': None, 'last_name': None,
            'last_progress': -1, 'last_speed': None,
        }
        self._update_dl_row(widgets, item)
        return widgets

    def _update_dl_row(self, w: dict, item: DownloadItem):
        """Update an existing row's fields in place without rebuilding widgets."""
        # State text + color
        if w['last_state'] != item.state:
            color = self._STATE_COLORS.get(item.state, TEXT_SEC)
            try:
                w['state_lbl'].configure(text=item.state or '—', text_color=color)
            except Exception:
                return
            w['last_state'] = item.state

        # Name (may arrive after creation once metadata is scraped)
        display_name = item.name or item.url
        if w['last_name'] != display_name:
            try:
                w['name_lbl'].configure(text=display_name)
            except Exception:
                return
            w['last_name'] = display_name

        # Progress bar: show only while downloading
        is_downloading = (item.state == '下載中' and item.progress > 0)
        if is_downloading:
            if not w['pb_visible']:
                w['pb'].pack(side='left', padx=4, before=w.get('_before_remove', None))
                # If before-widget ref not set, fall back to simple pack (still side='left')
                w['pb_visible'] = True
            if w['last_progress'] != item.progress:
                w['pb'].set(max(0.0, min(1.0, item.progress / 100)))
                w['last_progress'] = item.progress
            pct_text = f'{item.progress}%'
            if not w['pct_visible']:
                w['pct_lbl'].pack(side='left')
                w['pct_visible'] = True
            if w['pct_lbl'].cget('text') != pct_text:
                w['pct_lbl'].configure(text=pct_text)
        else:
            if w['pb_visible']:
                try: w['pb'].pack_forget()
                except Exception: pass
                w['pb_visible'] = False
            if w['pct_visible']:
                try: w['pct_lbl'].pack_forget()
                except Exception: pass
                w['pct_visible'] = False

        # Speed
        if item.speed:
            if not w['spd_visible']:
                w['spd_lbl'].pack(side='left', padx=4)
                w['spd_visible'] = True
            if w['last_speed'] != item.speed:
                w['spd_lbl'].configure(text=item.speed)
                w['last_speed'] = item.speed
        else:
            if w['spd_visible']:
                try: w['spd_lbl'].pack_forget()
                except Exception: pass
                w['spd_visible'] = False
                w['last_speed'] = None

    # ── Clipboard monitor (main-thread safe) ─────────────────────────
    def _clipboard_poll(self):
        if self._is_closing:
            return
        try:
            clp = self.clipboard_get()
            if clp != self._clp_text:
                self._clp_text = clp
                for m in re.finditer(r'https?://\S+', clp):
                    url = m.group(0).rstrip('.,;)\'"')
                    if M3U8Sites.VaildateUrl(url):
                        existing = {i.url for i in self._dlmgr.get_items()}
                        if url not in existing:
                            self._dlmgr.add_item(url)
                            print(f'[剪貼簿] {url}')
        except (tk.TclError, Exception):
            pass
        self.after(800, self._clipboard_poll)

    # ── Close ────────────────────────────────────────────────────────
    def _on_close(self):
        self._is_closing = True
        self._dlmgr.cancel_all()
        self._dlmgr.save_csv(CSV_PATH)
        self.destroy()


def gui_modern_main(url: str = '', dest: str = 'download'):
    app = ModernApp(url=url, dest=dest)
    app.mainloop()
