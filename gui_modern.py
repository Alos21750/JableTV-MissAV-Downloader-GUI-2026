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
from locales import T, set_lang, get_lang

# ── Design tokens ────────────────────────────────────────────────────
ACCENT       = '#e94560'
ACCENT_HOVER = '#d13a52'
ACCENT_DIM   = '#3a1524'
ACCENT2      = '#7b61ff'
ACCENT2_HOVER = '#6a50e0'
SUCCESS      = '#34d399'
SUCCESS_DIM  = '#0d3325'
WARNING      = '#fbbf24'
WARNING_DIM  = '#3a2e0d'
ERROR_C      = '#f87171'
ERROR_DIM    = '#3a1a1a'

BG_DARK      = '#0b0b19'
BG_CARD      = '#13132c'
BG_CARD_HOVER = '#1a1a38'
BG_INPUT     = '#181836'
BG_HEADER    = '#0e0e20'
BG_SECTION   = '#111126'
BG_SIDEBAR   = '#090916'
BG_BADGE     = '#1e1e3e'

TEXT_PRI     = '#eaeaf4'
TEXT_SEC     = '#9494b4'
TEXT_DIM     = '#585878'
TEXT_LINK    = '#8888cc'

BORDER       = '#242444'
BORDER_HOVER = '#343460'
BORDER_CARD  = '#1e1e3c'

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
    def __init__(self, url: str = '', dest: str = 'download', lang: str = 'zh'):
        super().__init__()

        set_lang(lang)
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
        # ── Header bar ──────────────────────────────────────────────
        header = ctk.CTkFrame(self, height=56, fg_color=BG_HEADER, corner_radius=0)
        header.pack(fill='x')
        header.pack_propagate(False)

        # Brand
        brand = ctk.CTkFrame(header, fg_color='transparent')
        brand.pack(side='left', padx=20, fill='y')
        ctk.CTkLabel(brand, text='JableTV & MissAV',
                     font=('Microsoft JhengHei', 17, 'bold'),
                     text_color=TEXT_PRI).pack(side='left', pady=0)
        ctk.CTkLabel(brand, text='Downloader',
                     font=('Microsoft JhengHei', 17),
                     text_color=ACCENT).pack(side='left', padx=(8, 0))

        # Right info
        ctk.CTkLabel(header, text='v2.1.5  |  by ALOS',
                     font=('Consolas', 10),
                     text_color=TEXT_DIM).pack(side='right', padx=20)

        # Header separator
        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(fill='x')

        # ── Tab view ────────────────────────────────────────────────
        self._tabs = ctk.CTkTabview(self, fg_color=BG_DARK,
                                     segmented_button_fg_color=BG_HEADER,
                                     segmented_button_selected_color=ACCENT,
                                     segmented_button_unselected_color=BG_CARD,
                                     segmented_button_selected_hover_color=ACCENT_HOVER,
                                     segmented_button_unselected_hover_color=BG_CARD_HOVER,
                                     corner_radius=0)
        self._tabs.pack(fill='both', expand=True, padx=0, pady=0)
        self._tabs.add(T('tab_browse'))
        self._tabs.add(T('tab_download'))
        self._tabs.add(T('tab_settings'))

        self._build_browse_tab()
        self._build_download_tab()
        self._build_settings_tab()

        # ── Status bar ──────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(fill='x')
        status_bar = ctk.CTkFrame(self, height=30, fg_color=BG_HEADER, corner_radius=0)
        status_bar.pack(fill='x')
        status_bar.pack_propagate(False)
        self._status_lbl = ctk.CTkLabel(status_bar, text='Ready',
                                         font=('Consolas', 10),
                                         text_color=TEXT_SEC)
        self._status_lbl.pack(side='left', padx=16)

    # ── Browse Tab ───────────────────────────────────────────────────
    def _build_browse_tab(self):
        tab = self._tabs.tab(T('tab_browse'))

        # ── Top toolbar ─────────────────────────────────────────────
        top = ctk.CTkFrame(tab, fg_color=BG_SECTION, corner_radius=0, height=54)
        top.pack(fill='x')
        top.pack_propagate(False)

        # Left group: Site + Category selectors
        left = ctk.CTkFrame(top, fg_color='transparent')
        left.pack(side='left', fill='y', padx=(16, 0))

        self._site_var = ctk.StringVar(value='JableTV')
        ctk.CTkLabel(left, text='Site', text_color=TEXT_DIM,
                     font=('Microsoft JhengHei', 9)).pack(side='left', padx=(0, 6))
        self._site_menu = ctk.CTkOptionMenu(
            left, values=list(SITES.keys()), variable=self._site_var,
            command=self._on_site_change, width=110,
            fg_color=BG_INPUT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, corner_radius=6)
        self._site_menu.pack(side='left', padx=(0, 8))

        # Vertical divider
        ctk.CTkFrame(left, width=1, fg_color=BORDER).pack(
            side='left', fill='y', pady=14, padx=6)

        ctk.CTkLabel(left, text=T('category_label'), text_color=TEXT_DIM,
                     font=('Microsoft JhengHei', 9)).pack(side='left', padx=(6, 6))
        self._cat_var = ctk.StringVar(value=T('loading_browse'))
        self._cat_menu = ctk.CTkOptionMenu(
            left, values=[T('loading_browse')], variable=self._cat_var,
            command=self._on_cat_change, width=170,
            fg_color=BG_INPUT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, corner_radius=6)
        self._cat_menu.pack(side='left')

        # Center: Search
        center = ctk.CTkFrame(top, fg_color='transparent')
        center.pack(side='left', fill='y', padx=16)

        self._search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(center, textvariable=self._search_var,
                                     placeholder_text=T('search_placeholder'),
                                     width=220, height=32,
                                     fg_color=BG_INPUT, border_color=BORDER,
                                     border_width=1, corner_radius=6,
                                     text_color=TEXT_PRI)
        search_entry.pack(side='left', padx=(0, 6))
        search_entry.bind('<Return>', lambda e: self._on_search())
        ctk.CTkButton(center, text=T('search_btn'), command=self._on_search,
                      width=64, height=32, corner_radius=6,
                      fg_color=ACCENT,
                      hover_color=ACCENT_HOVER).pack(side='left')

        # Right: Selection controls
        right = ctk.CTkFrame(top, fg_color='transparent')
        right.pack(side='right', fill='y', padx=(0, 16))

        self._sel_lbl = ctk.CTkLabel(right, text='', text_color=ACCENT,
                                      font=('Microsoft JhengHei', 11, 'bold'))
        self._sel_lbl.pack(side='right', padx=8)
        ctk.CTkButton(right, text=T('select_all_btn'), command=self._select_all_on_page,
                      width=80, height=32, corner_radius=6,
                      fg_color=BG_CARD, border_width=1, border_color=BORDER,
                      hover_color=BG_CARD_HOVER,
                      text_color=TEXT_PRI).pack(side='right', padx=4)
        ctk.CTkButton(right, text=T('download_selected'), command=self._download_selected,
                      width=100, height=32, corner_radius=6,
                      fg_color=ACCENT,
                      hover_color=ACCENT_HOVER).pack(side='right', padx=4)
        ctk.CTkButton(right, text=T('clear_list'), command=self._add_selected_to_queue,
                      width=80, height=32, corner_radius=6,
                      fg_color=BG_CARD, border_width=1, border_color=BORDER,
                      hover_color=BG_CARD_HOVER,
                      text_color=TEXT_PRI).pack(side='right', padx=4)

        # ── Content area: sidebar + grid ────────────────────────────
        content = ctk.CTkFrame(tab, fg_color=BG_DARK, corner_radius=0)
        content.pack(fill='both', expand=True)

        # Sidebar
        self._sidebar = ctk.CTkScrollableFrame(
            content, width=145, fg_color=BG_SIDEBAR,
            corner_radius=0, scrollbar_button_color=BORDER)
        self._sidebar.pack(side='left', fill='y')

        # Video grid area
        grid_area = ctk.CTkFrame(content, fg_color=BG_DARK, corner_radius=0)
        grid_area.pack(side='left', fill='both', expand=True)

        self._grid_scroll = ctk.CTkScrollableFrame(
            grid_area, fg_color=BG_DARK, corner_radius=0)
        self._grid_scroll.pack(fill='both', expand=True)

        # ── Navigation bar ──────────────────────────────────────────
        nav = ctk.CTkFrame(tab, fg_color=BG_HEADER, corner_radius=0, height=44)
        nav.pack(fill='x')
        nav.pack_propagate(False)

        nav_inner = ctk.CTkFrame(nav, fg_color='transparent')
        nav_inner.pack(pady=6)

        ctk.CTkButton(nav_inner, text=T('first_page'), width=64, height=30,
                      corner_radius=6,
                      fg_color=BG_CARD, border_width=1, border_color=BORDER,
                      hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
                      command=lambda: self._goto_page(1)).pack(side='left', padx=3)
        ctk.CTkButton(nav_inner, text=T('prev_page'), width=74, height=30,
                      corner_radius=6,
                      fg_color=BG_CARD, border_width=1, border_color=BORDER,
                      hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
                      command=lambda: self._goto_page(self._page - 1)
                      ).pack(side='left', padx=3)
        self._page_lbl = ctk.CTkLabel(nav_inner, text=T('page_n', n=1), text_color=TEXT_PRI,
                                       font=('Microsoft JhengHei', 12, 'bold'),
                                       width=80)
        self._page_lbl.pack(side='left', padx=10)
        ctk.CTkButton(nav_inner, text=T('next_page'), width=74, height=30,
                      corner_radius=6,
                      fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=lambda: self._goto_page(self._page + 1)
                      ).pack(side='left', padx=3)

        # Page jump input
        ctk.CTkFrame(nav_inner, width=1, fg_color=BORDER).pack(
            side='left', fill='y', pady=4, padx=10)
        self._page_jump_var = ctk.StringVar(value='')
        page_entry = ctk.CTkEntry(nav_inner, textvariable=self._page_jump_var,
                                   width=50, height=30, corner_radius=6,
                                   fg_color=BG_INPUT, border_color=BORDER,
                                   border_width=1, text_color=TEXT_PRI,
                                   placeholder_text='#',
                                   justify='center')
        page_entry.pack(side='left', padx=3)
        page_entry.bind('<Return>', lambda e: self._jump_to_page())
        ctk.CTkButton(nav_inner, text='Go', width=40, height=30,
                      corner_radius=6,
                      fg_color=BG_CARD, border_width=1, border_color=BORDER,
                      hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
                      command=self._jump_to_page).pack(side='left', padx=3)

        self._rebuild_sidebar()

    # ── Download Tab ─────────────────────────────────────────────────
    def _build_download_tab(self):
        tab = self._tabs.tab(T('tab_download'))

        # ── Input section ───────────────────────────────────────────
        input_frame = ctk.CTkFrame(tab, fg_color=BG_SECTION, corner_radius=0)
        input_frame.pack(fill='x')

        # Save location
        row1 = ctk.CTkFrame(input_frame, fg_color='transparent')
        row1.pack(fill='x', padx=16, pady=(12, 4))
        ctk.CTkLabel(row1, text=T('save_location'), text_color=TEXT_DIM, width=70,
                     font=('Microsoft JhengHei', 10), anchor='e').pack(side='left')
        self._dest_var = ctk.StringVar(value=self._dest)
        ctk.CTkEntry(row1, textvariable=self._dest_var,
                     height=34, corner_radius=6,
                     fg_color=BG_INPUT, border_color=BORDER, border_width=1,
                     text_color=TEXT_PRI).pack(side='left', fill='x',
                                               expand=True, padx=10)
        ctk.CTkButton(row1, text=T('browse_folder'), width=60, height=34, corner_radius=6,
                      fg_color=BG_CARD, border_width=1, border_color=BORDER,
                      hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
                      command=self._pick_dest).pack(side='left')
        ctk.CTkButton(row1, text='Open', width=50, height=34, corner_radius=6,
                      fg_color=BG_CARD, border_width=1, border_color=BORDER,
                      hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
                      command=self._open_dest_folder).pack(side='left', padx=(6, 0))

        # Download URL
        row2 = ctk.CTkFrame(input_frame, fg_color='transparent')
        row2.pack(fill='x', padx=16, pady=(0, 12))
        ctk.CTkLabel(row2, text=T('url_label'), text_color=TEXT_DIM, width=70,
                     font=('Microsoft JhengHei', 10), anchor='e').pack(side='left')
        self._dl_url_var = ctk.StringVar(value=self._url_input)
        ctk.CTkEntry(row2, textvariable=self._dl_url_var,
                     height=34, corner_radius=6,
                     fg_color=BG_INPUT, border_color=BORDER, border_width=1,
                     text_color=TEXT_PRI).pack(side='left', fill='x',
                                               expand=True, padx=10)

        # Separator
        ctk.CTkFrame(tab, height=1, fg_color=BORDER, corner_radius=0).pack(fill='x')

        # ── Action bar ──────────────────────────────────────────────
        bar = ctk.CTkFrame(tab, fg_color=BG_HEADER, corner_radius=0, height=50)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        # Primary actions (left)
        ctk.CTkButton(bar, text=T('download_btn'), width=95, height=34, corner_radius=6,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=('Microsoft JhengHei', 11, 'bold'),
                      command=self._download_url).pack(side='left', padx=(12, 4), pady=8)
        ctk.CTkButton(bar, text=T('download_all_btn'), width=120, height=34, corner_radius=6,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._download_all).pack(side='left', padx=4)

        # Left separator
        ctk.CTkFrame(bar, width=1, fg_color=BORDER).pack(
            side='left', fill='y', pady=12, padx=8)

        # Destructive actions (right)
        ctk.CTkButton(bar, text=T('clear_list'), width=60, height=34, corner_radius=6,
                      fg_color=ERROR_DIM, border_width=1, border_color='#4a2020',
                      hover_color='#2a1215', text_color=ERROR_C,
                      command=self._clear_queue).pack(side='right', padx=(4, 12), pady=8)
        ctk.CTkButton(bar, text=T('cancel_all'), width=80, height=34, corner_radius=6,
                      fg_color=ERROR_DIM, border_width=1, border_color='#4a2020',
                      hover_color='#2a1215', text_color=ERROR_C,
                      command=self._cancel_all).pack(side='right', padx=4)

        # Right separator
        ctk.CTkFrame(bar, width=1, fg_color=BORDER).pack(
            side='right', fill='y', pady=12, padx=8)

        # Speed control
        ctk.CTkLabel(bar, text=T('speed_limit'), text_color=TEXT_DIM,
                     font=('Microsoft JhengHei', 9)).pack(side='right', padx=(0, 6))
        self._speed_var = ctk.StringVar(value=T('unlimited'))
        ctk.CTkOptionMenu(bar, values=[T('unlimited'), '1 MB/s', '2 MB/s', '5 MB/s',
                                        '10 MB/s', '15 MB/s'],
                          variable=self._speed_var,
                          command=self._on_speed_change, width=100, height=34,
                          corner_radius=6,
                          fg_color=BG_INPUT, button_color=ACCENT,
                          button_hover_color=ACCENT_HOVER
                          ).pack(side='right', padx=4, pady=8)

        # Separator under action bar
        ctk.CTkFrame(tab, height=1, fg_color=BORDER, corner_radius=0).pack(fill='x')

        # ── Download list ───────────────────────────────────────────
        self._dl_scroll = ctk.CTkScrollableFrame(
            tab, fg_color=BG_DARK, corner_radius=0)
        self._dl_scroll.pack(fill='both', expand=True)

    # ── Settings Tab ─────────────────────────────────────────────────
    def _build_settings_tab(self):
        tab = self._tabs.tab(T('tab_settings'))

        outer = ctk.CTkScrollableFrame(tab, fg_color=BG_DARK, corner_radius=0)
        outer.pack(fill='both', expand=True)

        # Content container
        content = ctk.CTkFrame(outer, fg_color='transparent')
        content.pack(fill='x', padx=40, pady=24)

        # ── Page title ──────────────────────────────────────────────
        title_row = ctk.CTkFrame(content, fg_color='transparent')
        title_row.pack(fill='x', pady=(0, 20))
        ctk.CTkLabel(title_row, text=T('settings_title'),
                     font=('Microsoft JhengHei', 20, 'bold'),
                     text_color=TEXT_PRI).pack(side='left')
        ctk.CTkLabel(title_row, text=T('settings_desc'),
                     font=('Microsoft JhengHei', 10),
                     text_color=TEXT_DIM).pack(side='left', padx=(16, 0))

        # ── Download Settings Card ──────────────────────────────────
        grp = ctk.CTkFrame(content, fg_color=BG_SECTION, corner_radius=12,
                            border_width=1, border_color=BORDER)
        grp.pack(fill='x', pady=(0, 16))

        # Card header
        grp_hdr = ctk.CTkFrame(grp, fg_color='transparent')
        grp_hdr.pack(fill='x', padx=20, pady=(16, 12))
        ctk.CTkLabel(grp_hdr, text=T('download_settings'),
                     font=('Microsoft JhengHei', 14, 'bold'),
                     text_color=TEXT_PRI).pack(side='left')

        ctk.CTkFrame(grp, height=1, fg_color=BORDER).pack(fill='x', padx=20)

        # Save location
        row_dest = ctk.CTkFrame(grp, fg_color='transparent')
        row_dest.pack(fill='x', padx=20, pady=(16, 2))
        ctk.CTkLabel(row_dest, text=T('save_location_setting'), text_color=TEXT_PRI,
                     font=('Microsoft JhengHei', 11), width=90,
                     anchor='w').pack(side='left')
        ctk.CTkEntry(row_dest, textvariable=self._dest_var,
                     height=34, corner_radius=6,
                     fg_color=BG_INPUT, border_color=BORDER, border_width=1,
                     text_color=TEXT_PRI).pack(side='left', fill='x',
                                               expand=True, padx=10)
        ctk.CTkButton(row_dest, text=T('browse_folder'), width=60, height=34, corner_radius=6,
                      fg_color=BG_CARD, border_width=1, border_color=BORDER,
                      hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
                      command=self._pick_dest).pack(side='left')
        ctk.CTkLabel(grp, text=T('save_location_desc'),
                     text_color=TEXT_DIM,
                     font=('Microsoft JhengHei', 9)).pack(anchor='w', padx=(110, 0), pady=(0, 8))

        # Speed limit
        row_speed = ctk.CTkFrame(grp, fg_color='transparent')
        row_speed.pack(fill='x', padx=20, pady=(8, 2))
        ctk.CTkLabel(row_speed, text=T('speed_limit_setting'), text_color=TEXT_PRI,
                     font=('Microsoft JhengHei', 11), width=90,
                     anchor='w').pack(side='left')
        ctk.CTkOptionMenu(row_speed, values=[T('unlimited'), '1 MB/s', '2 MB/s',
                                              '5 MB/s', '10 MB/s', '15 MB/s'],
                          variable=self._speed_var,
                          command=self._on_speed_change, width=130, height=34,
                          corner_radius=6,
                          fg_color=BG_INPUT, button_color=ACCENT,
                          button_hover_color=ACCENT_HOVER).pack(side='left', padx=10)
        ctk.CTkLabel(grp, text=T('speed_limit_desc'),
                     text_color=TEXT_DIM,
                     font=('Microsoft JhengHei', 9)).pack(anchor='w', padx=(110, 0), pady=(0, 8))

        # Concurrent downloads
        row_conc = ctk.CTkFrame(grp, fg_color='transparent')
        row_conc.pack(fill='x', padx=20, pady=(8, 2))
        ctk.CTkLabel(row_conc, text=T('concurrent_setting'), text_color=TEXT_PRI,
                     font=('Microsoft JhengHei', 11), width=90,
                     anchor='w').pack(side='left')
        self._conc_var = ctk.StringVar(value=str(DEFAULT_CONCURRENT))
        ctk.CTkOptionMenu(row_conc,
                          values=[str(i) for i in range(1, MAX_CONCURRENT + 1)],
                          variable=self._conc_var,
                          command=self._on_conc_change, width=80, height=34,
                          corner_radius=6,
                          fg_color=BG_INPUT, button_color=ACCENT,
                          button_hover_color=ACCENT_HOVER).pack(side='left', padx=10)
        ctk.CTkLabel(row_conc, text=T('max_n', n=MAX_CONCURRENT),
                     text_color=TEXT_DIM,
                     font=('Microsoft JhengHei', 10)).pack(side='left')
        ctk.CTkLabel(grp, text=T('concurrent_desc'),
                     text_color=TEXT_DIM,
                     font=('Microsoft JhengHei', 9)).pack(anchor='w', padx=(110, 0), pady=(0, 20))

        # ── About Card ──────────────────────────────────────────────
        about = ctk.CTkFrame(content, fg_color=BG_SECTION, corner_radius=12,
                              border_width=1, border_color=BORDER)
        about.pack(fill='x', pady=(0, 16))

        about_hdr = ctk.CTkFrame(about, fg_color='transparent')
        about_hdr.pack(fill='x', padx=20, pady=(16, 12))
        ctk.CTkLabel(about_hdr, text=T('about'),
                     font=('Microsoft JhengHei', 14, 'bold'),
                     text_color=TEXT_PRI).pack(side='left')

        ctk.CTkFrame(about, height=1, fg_color=BORDER).pack(fill='x', padx=20)

        about_body = ctk.CTkFrame(about, fg_color='transparent')
        about_body.pack(fill='x', padx=20, pady=16)

        ctk.CTkLabel(about_body, text='JableTV & MissAV Downloader',
                     text_color=TEXT_PRI,
                     font=('Microsoft JhengHei', 15, 'bold')).pack(anchor='w')
        ctk.CTkLabel(about_body, text='by ALOS (Alos21750)',
                     text_color=ACCENT,
                     font=('Microsoft JhengHei', 12)).pack(anchor='w', pady=(6, 0))

        # Version badge
        ver_badge = ctk.CTkFrame(about_body, fg_color=BG_BADGE, corner_radius=4)
        ver_badge.pack(anchor='w', pady=(10, 0))
        ctk.CTkLabel(ver_badge, text='v2.1.5',
                     text_color=TEXT_SEC,
                     font=('Consolas', 10)).pack(padx=10, pady=4)

        ctk.CTkLabel(about_body, text=T('disclaimer'),
                     text_color=TEXT_DIM,
                     font=('Microsoft JhengHei', 10)).pack(anchor='w', pady=(10, 0))

    # ── Browse logic ─────────────────────────────────────────────────
    def _load_categories(self):
        browser = SITES[self._site_key]['browser']
        try:
            if self._site_key == 'MissAV':
                cats = browser.fetch_categories(lang=T('missav_lang'))
            else:
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
                text=T('page_n', n=self._page)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _refresh_grid(self):
        for w in self._grid_scroll.winfo_children():
            w.destroy()
        self._card_widgets = {}

        if not self._videos:
            ctk.CTkLabel(self._grid_scroll, text=T('no_results'),
                         text_color=TEXT_DIM,
                         font=('Microsoft JhengHei', 14)).pack(pady=40)
            return

        self._grid_gen += 1
        gen = self._grid_gen

        # Create grid of cards, 4 per row
        row_frame = None
        for i, v in enumerate(self._videos):
            if i % 4 == 0:
                row_frame = ctk.CTkFrame(self._grid_scroll, fg_color='transparent')
                row_frame.pack(fill='x', padx=10, pady=4)

            url = v.get('url', '')
            title = v.get('title', '')
            dur = v.get('duration', '')
            thumb_url = v.get('thumbnail', '')
            is_sel = url in self._selected_urls

            card = ctk.CTkFrame(row_frame, fg_color=BG_CARD, corner_radius=10,
                                border_width=2,
                                border_color=ACCENT if is_sel else BORDER)
            card.pack(side='left', padx=5, pady=5, fill='x', expand=True)

            # Thumbnail placeholder (16:9)
            thumb_holder = ctk.CTkFrame(card, fg_color=BG_SIDEBAR,
                                         height=_THUMB_SIZE[1], corner_radius=8)
            thumb_holder.pack(fill='x', padx=8, pady=(8, 0))
            thumb_holder.pack_propagate(False)
            thumb_lbl = ctk.CTkLabel(thumb_holder, text=T('loading_browse'),
                                      text_color=TEXT_DIM,
                                      fg_color='transparent',
                                      font=('Microsoft JhengHei', 10))
            thumb_lbl.pack(expand=True)

            # Duration badge
            if dur:
                dur_lbl = ctk.CTkLabel(thumb_holder, text=f' {dur} ',
                                        text_color='#ffffff',
                                        fg_color='#000000',
                                        corner_radius=4,
                                        font=('Consolas', 9, 'bold'))
                dur_lbl.place(relx=1.0, rely=1.0, anchor='se', x=-6, y=-6)

            # Title
            title_text = title[:55] + '...' if len(title) > 55 else title
            ctk.CTkLabel(card, text=title_text, text_color=TEXT_PRI,
                         font=('Microsoft JhengHei', 10),
                         wraplength=230, justify='left').pack(
                padx=10, pady=(8, 2), anchor='w')

            # Bottom row
            bottom = ctk.CTkFrame(card, fg_color='transparent')
            bottom.pack(fill='x', padx=10, pady=(0, 10))

            sel_text = ('✓ ' + T('selected')) if is_sel else T('select')
            sel_btn = ctk.CTkButton(
                bottom, text=sel_text, width=64, height=26,
                corner_radius=6,
                fg_color=ACCENT if is_sel else BG_INPUT,
                hover_color=ACCENT_HOVER,
                font=('Microsoft JhengHei', 9),
                command=lambda u=url: self._toggle_select(u)
            )
            sel_btn.pack(side='right')

            self._card_widgets[url] = {'card': card, 'sel_btn': sel_btn}

            # Clickable card
            def _bind_click(widget, video_url=url):
                widget.bind('<Button-1>', lambda e, u=video_url: self._toggle_select(u))
                widget.configure(cursor='hand2')
            _bind_click(card)
            _bind_click(thumb_holder)
            _bind_click(thumb_lbl)

            # Background thumbnail load
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
                    text=('✓ ' + T('selected')) if is_sel else T('select'),
                    fg_color=ACCENT if is_sel else BG_INPUT)
            except Exception:
                pass
        n = len(self._selected_urls)
        self._sel_lbl.configure(text=f'{n} {T("selected")}' if n else '')

    def _goto_page(self, p: int):
        if p < 1:
            return
        self._page = p
        self._load_page()

    def _jump_to_page(self):
        """Jump to page number entered in the page-jump field."""
        try:
            p = int(self._page_jump_var.get().strip())
            if p >= 1:
                self._goto_page(p)
        except (ValueError, TypeError):
            pass
        self._page_jump_var.set('')

    def _select_all_on_page(self):
        """Select all videos currently displayed on the page."""
        for v in self._videos:
            url = v.get('url', '')
            if url:
                self._selected_urls.add(url)
        self._refresh_grid()
        n = len(self._selected_urls)
        self._sel_lbl.configure(text=f'{n} {T("selected")}' if n else '')

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
            lang = T('missav_lang')
            self._current_base_url = f'https://missav.ai/dm265/{lang}/search?query={q}'
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
                     font=('Microsoft JhengHei', 12, 'bold')).pack(
            anchor='w', padx=10, pady=(10, 6))

        # Subtle divider
        ctk.CTkFrame(self._sidebar, height=1,
                     fg_color=BORDER).pack(fill='x', padx=8, pady=(0, 6))

        if self._site_key != 'JableTV':
            ctk.CTkLabel(self._sidebar, text='僅 JableTV\n支援標籤',
                         text_color=TEXT_DIM,
                         font=('Microsoft JhengHei', 10)).pack(pady=20)
            return

        tags = JableTVBrowser.SIDEBAR_TAGS
        for group_name, tag_list in tags.items():
            expanded = self._sidebar_expanded.get(group_name, False)

            # Group header button
            arrow = '▾' if expanded else '▸'
            hdr = ctk.CTkButton(
                self._sidebar,
                text=f'{arrow} {group_name} ({len(tag_list)})',
                fg_color='transparent', hover_color='#141430',
                text_color=TEXT_SEC, anchor='w',
                font=('Microsoft JhengHei', 10, 'bold'),
                height=30, corner_radius=4,
                command=lambda g=group_name: self._toggle_group(g))
            hdr.pack(fill='x', padx=4, pady=1)

            if expanded:
                for name, slug in tag_list:
                    tag_url = JableTVBrowser.tag_url(slug)
                    btn = ctk.CTkButton(
                        self._sidebar, text=name,
                        fg_color='transparent', hover_color='#1a1a34',
                        text_color=TEXT_SEC, anchor='w',
                        font=('Microsoft JhengHei', 10),
                        height=26, corner_radius=4,
                        command=lambda u=tag_url, n=name: self._on_tag_click(u, n))
                    btn.pack(fill='x', padx=(16, 4), pady=0)

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
        # Direct video URL
        if M3U8Sites.VaildateUrl(url):
            dest = self._dest_var.get() or 'download'
            self._dlmgr.add_item(url, state='等待中')
            self._dlmgr.enqueue(url, dest)
            self._dl_url_var.set('')
            return
        # Listing / actress / category URL — crawl all videos
        if self._is_listing_url(url):
            self._dl_url_var.set('')
            self._status_lbl.configure(text=T('crawling_url'))
            threading.Thread(target=self._crawl_listing, args=(url,),
                             daemon=True).start()
            return
        self._status_lbl.configure(text=T('url_not_supported'))
        print(T('url_not_supported') + f': {url}')

    def _is_listing_url(self, url: str) -> bool:
        """Check if URL is a JableTV or MissAV listing/category/actress page."""
        return (url.startswith('https://jable.tv/') or
                bool(re.match(r'https://(?:www\.)?missav\.(?:ai|ws)/', url)))

    def _crawl_listing(self, url: str):
        """Crawl a listing URL across all pages; add every video to the queue."""
        dest = self._dest_var.get() or 'download'
        seen: set[str] = set()
        is_jable = url.startswith('https://jable.tv/')
        max_pages = 50

        for page in range(1, max_pages + 1):
            try:
                if is_jable:
                    if page == 1:
                        page_url = url
                    elif '?' in url:
                        page_url = f'{url}&from_videos={page}'
                    else:
                        page_url = f'{url.rstrip("/")}/?from={page}'
                    videos = JableTVBrowser.fetch_page(page_url)
                else:
                    page_url = MissAVBrowser.page_url(url, page)
                    videos = MissAVBrowser.fetch_page(page_url)
            except Exception as e:
                print(f'[crawl] page {page} error: {e}')
                break

            if not videos:
                if page == 1:
                    print(f'[crawl] No videos found on first page: {url}')
                break

            new_count = 0
            for v in videos:
                video_url = v.get('url', '')
                if video_url and video_url not in seen and M3U8Sites.VaildateUrl(video_url):
                    seen.add(video_url)
                    new_count += 1
                    name = v.get('title', '')
                    self._dlmgr.add_item(video_url, name=name, state='等待中')
                    self._dlmgr.enqueue(video_url, dest)

            if new_count == 0:
                break  # No new videos on this page, stop

            self.after(0, lambda n=len(seen): self._status_lbl.configure(
                text=T('crawling_url') + f' ({n})'))

        n = len(seen)
        self.after(0, lambda: self._status_lbl.configure(
            text=T('crawl_added', n=n)))

    def _download_all(self):
        # If the URL field has a listing URL, crawl it first
        url = self._dl_url_var.get().strip()
        if url:
            if M3U8Sites.VaildateUrl(url):
                dest = self._dest_var.get() or 'download'
                self._dlmgr.add_item(url, state='等待中')
                self._dlmgr.enqueue(url, dest)
                self._dl_url_var.set('')
            elif self._is_listing_url(url):
                self._dl_url_var.set('')
                self._status_lbl.configure(text=T('crawling_url'))
                threading.Thread(target=self._crawl_listing, args=(url,),
                                 daemon=True).start()
                return
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
        if val in ('無限制', 'Unlimited'):
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
                    font=('Microsoft JhengHei', 13))
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

        row = ctk.CTkFrame(self._dl_scroll, fg_color=BG_CARD, corner_radius=6,
                           border_width=1, border_color=BORDER_CARD,
                           height=48)
        row.pack(fill='x', padx=6, pady=3)
        row.pack_propagate(False)

        state_lbl = ctk.CTkLabel(row, text=item.state or '—', text_color=color,
                                 font=('Microsoft JhengHei', 10, 'bold'),
                                 width=68)
        state_lbl.pack(side='left', padx=(12, 4))

        name_lbl = ctk.CTkLabel(row, text=item.name or item.url,
                                text_color=TEXT_PRI,
                                font=('Microsoft JhengHei', 10),
                                anchor='w')
        name_lbl.pack(side='left', fill='x', expand=True, padx=6)

        # Progress widgets (created once, packed/unpacked dynamically)
        pb = ctk.CTkProgressBar(row, width=130, height=10,
                                corner_radius=5,
                                fg_color='#1a1a2e',
                                progress_color=ACCENT)
        pb.set(max(0.0, min(1.0, item.progress / 100)))
        pct_lbl = ctk.CTkLabel(row, text='', text_color=TEXT_SEC,
                               font=('Consolas', 9), width=40)
        spd_lbl = ctk.CTkLabel(row, text='', text_color=TEXT_SEC,
                               font=('Consolas', 9), width=80)

        # Remove button
        remove_btn = ctk.CTkButton(
            row, text='✕', width=30, height=30,
            corner_radius=6,
            fg_color='transparent', hover_color=ERROR_DIM,
            text_color=TEXT_DIM, font=('Consolas', 12),
            command=lambda u=item.url: self._dlmgr.remove_item(u))
        remove_btn.pack(side='right', padx=6)

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


def gui_modern_main(url: str = '', dest: str = 'download', lang: str = 'zh'):
    app = ModernApp(url=url, dest=dest, lang=lang)
    app.mainloop()
