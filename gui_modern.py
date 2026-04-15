#!/usr/bin/env python
# coding: utf-8
"""Modern GUI for JableTV & MissAV Downloader — built with NiceGUI (Quasar/Vue)."""

import os
import sys
import re
import csv
import time
import threading
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from nicegui import ui, app, events

import M3U8Sites
from M3U8Sites.SiteJableTV import JableTVBrowser
from M3U8Sites.SiteMissAV import MissAVBrowser
from config import headers

# ── Design tokens ────────────────────────────────────────────────────
ACCENT = '#e94560'
ACCENT2 = '#7b61ff'
SUCCESS = '#4ade80'
WARNING = '#fbbf24'
ERROR_C = '#f87171'

MAX_CONCURRENT = 10
CSV_PATH = os.path.join(os.getcwd(), 'JableTV.csv')


# ── Download state ───────────────────────────────────────────────────
@dataclass
class DownloadItem:
    url: str
    name: str = ''
    state: str = ''
    progress: int = 0
    speed: str = ''


class DownloadManager:
    """Manages concurrent downloads with queue and state tracking."""

    def __init__(self, on_update=None):
        self._on_update = on_update
        self._pending: list[tuple[str, str]] = []
        self._active: dict[str, object] = {}
        self._items: dict[str, DownloadItem] = {}
        self._lock = threading.Lock()
        # Gate: only 1 item can query the site at a time (prevents
        # CloudFlare rate-limiting when many downloads are queued)
        self._prep_sem = threading.Semaphore(1)

    @property
    def active_count(self):
        with self._lock:
            return len(self._active)

    @property
    def pending_count(self):
        with self._lock:
            return len(self._pending)

    def get_items(self) -> list[DownloadItem]:
        with self._lock:
            return list(self._items.values())

    def add_item(self, url: str, name: str = '', state: str = '') -> None:
        with self._lock:
            if url not in self._items:
                self._items[url] = DownloadItem(
                    url=url,
                    name=name or url.rstrip('/').split('/')[-1],
                    state=state)
                self._notify()

    def enqueue(self, url: str, dest: str) -> None:
        with self._lock:
            if url in self._active:
                return
            if any(u == url for u, _ in self._pending):
                return
            if url not in self._items:
                self._items[url] = DownloadItem(
                    url=url, name=url.rstrip('/').split('/')[-1])
            if len(self._active) < MAX_CONCURRENT:
                self._active[url] = None
                threading.Thread(target=self._run, args=(url, dest),
                                 daemon=True).start()
            else:
                self._pending.append((url, dest))
                self._items[url].state = '等待中'
                self._notify()

    def cancel_all(self):
        with self._lock:
            for u, _ in self._pending:
                if u in self._items:
                    self._items[u].state = '已取消'
            self._pending.clear()
            jobs = list(self._active.items())
        for url, job in jobs:
            if job:
                try:
                    job.cancel_download()
                except Exception:
                    pass
            with self._lock:
                if url in self._items:
                    self._items[url].state = '已取消'
        with self._lock:
            self._active.clear()
        self._notify()

    def remove_item(self, url: str) -> None:
        with self._lock:
            self._pending = [(u, d) for u, d in self._pending if u != url]
            self._items.pop(url, None)
            job = self._active.pop(url, None)
        if job:
            try:
                job.cancel_download()
            except Exception:
                pass
        self._notify()

    def clear_all(self) -> None:
        self.cancel_all()
        with self._lock:
            self._items.clear()
        self._notify()

    def _run(self, url: str, dest: str):
        self._set_state(url, '準備中')
        try:
            # Serialize preparation: only one item queries the site at a
            # time to avoid CloudFlare rate-limiting on bulk downloads.
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
            job._progress_callback = lambda d, t, s: self._handle_progress(url, d, t, s)
            job.start_download()
            with self._lock:
                self._active.pop(url, None)
            if job._cancel_job:
                self._set_state(url, '已取消')
            else:
                self._set_state(url, '已下載', progress=100, speed='')
        except Exception as exc:
            print(f'[下載失敗] {url}\n  {exc}', flush=True)
            with self._lock:
                self._active.pop(url, None)
            self._set_state(url, '未完成')
        self._try_next()

    def _try_next(self):
        with self._lock:
            if not self._pending or len(self._active) >= MAX_CONCURRENT:
                return
            url, dest = self._pending.pop(0)
            self._active[url] = None
        threading.Thread(target=self._run, args=(url, dest), daemon=True).start()

    def _set_state(self, url: str, state: str, name: str = '',
                   progress: int = -1, speed: str = ''):
        with self._lock:
            item = self._items.get(url)
            if not item:
                return
            item.state = state
            if name:
                item.name = name
            if progress >= 0:
                item.progress = progress
            if speed is not None:
                item.speed = speed
        self._notify()

    def _handle_progress(self, url: str, done: int, total: int, speed_bps: float):
        if total <= 0:
            return
        pct = int(done * 100 / total)
        spd = (f'{speed_bps / 1024:.0f} KB/s' if speed_bps < 1024 * 1024
               else f'{speed_bps / 1024 / 1024:.1f} MB/s')
        self._set_state(url, '下載中', progress=pct, speed=spd)

    def _notify(self):
        if self._on_update:
            self._on_update()

    def save_csv(self, path: str):
        items = self.get_items()
        if not items:
            return
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['狀態', '名稱', '進度', '速度', '網址'])
            for item in items:
                w.writerow([item.state, item.name,
                            f'{item.progress}%' if item.progress else '',
                            item.speed, item.url])

    def load_csv(self, path: str):
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                url = row.get('網址', '')
                if url:
                    self.add_item(url, row.get('名稱', ''), row.get('狀態', ''))


# ── UI State ─────────────────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.site_key = 'JableTV'
        self.categories: list[dict] = []
        self.current_cat_idx = 0
        self.page = 1
        self.has_next = True
        self.current_base_url = ''
        self.search_query = ''
        self.videos: list[dict] = []
        self.selected_urls: set[str] = set()
        self.loading = False
        self.dest = 'download'
        self.url_input = ''
        self.console_lines: list[str] = []
        self.sidebar_expanded: dict[str, bool] = {}


# ── Browser logic ────────────────────────────────────────────────────
SITES = {
    'JableTV': {'browser': JableTVBrowser},
    'MissAV': {'browser': MissAVBrowser},
}


def build_page_url(state: AppState) -> str:
    if state.site_key == 'JableTV':
        base = state.current_base_url
        if '?' in base:
            return f'{base}&from_videos={state.page}'
        return f'{base.rstrip("/")}/?from={state.page}'
    return MissAVBrowser.page_url(state.current_base_url, state.page)


# ── Main UI ──────────────────────────────────────────────────────────
def gui_modern_main(url: str = '', dest: str = 'download'):
    state = AppState()
    state.dest = dest
    state.url_input = url

    dlmgr = DownloadManager()
    dlmgr.load_csv(CSV_PATH)

    # NiceGUI update bridge: schedule UI refresh from download threads
    def on_dl_update():
        try:
            ui.run_javascript('', respond=False)
        except Exception:
            pass

    dlmgr._on_update = on_dl_update

    # ── Custom dark theme CSS ────────────────────────────────────
    ui.add_head_html('''
    <style>
    :root {
        --q-dark: #0d0d18;
        --q-dark-page: #0a0a14;
        --q-primary: #e94560;
        --q-secondary: #7b61ff;
    }
    body { background: #0d0d18; }
    .q-drawer { background: #0a0a16 !important; }
    .q-header { background: #101020 !important; }
    .q-tab-panel { background: #0d0d18 !important; padding: 0 !important; }
    .q-footer { background: #101020 !important; }
    .video-card {
        background: #161630;
        border: 2px solid #2a2a48;
        border-radius: 8px;
        overflow: hidden;
        cursor: pointer;
        transition: border-color 0.2s, transform 0.15s;
    }
    .video-card:hover {
        border-color: #7b61ff;
        transform: translateY(-2px);
    }
    .video-card.selected {
        border-color: #e94560;
        border-width: 3px;
    }
    .video-card .thumb-container {
        position: relative;
        width: 100%;
        padding-top: 56.25%;
        background: #0a0a18;
        overflow: hidden;
    }
    .video-card .thumb-container img {
        position: absolute;
        top: 0; left: 0; width: 100%; height: 100%;
        object-fit: cover;
    }
    .video-card .duration-badge {
        position: absolute;
        bottom: 4px; right: 4px;
        background: rgba(0,0,0,0.8);
        color: #fff;
        font-size: 11px;
        font-family: monospace;
        padding: 1px 5px;
        border-radius: 3px;
    }
    .video-card .card-title {
        padding: 8px 10px;
        color: #f0f0f8;
        font-size: 13px;
        line-height: 1.35;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    .tag-btn {
        color: #a0a0c0;
        font-size: 13px;
        padding: 4px 12px 4px 20px;
        cursor: pointer;
        transition: background 0.15s, color 0.15s;
        user-select: none;
    }
    .tag-btn:hover { background: #1a1a30; color: #e94560; }
    .group-header {
        background: #0e0e20;
        padding: 6px 10px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 6px;
        user-select: none;
    }
    .group-header:hover { background: #141430; }
    .dl-table .q-table__container { background: #161630 !important; }
    .console-box {
        background: #0a0a14;
        color: #f0f0f8;
        font-family: 'Consolas', monospace;
        font-size: 12px;
        padding: 10px;
        height: 150px;
        overflow-y: auto;
        border-top: 1px solid #222240;
    }
    .status-chip {
        font-size: 11px;
        font-weight: bold;
    }
    </style>
    ''')

    @ui.page('/')
    async def main_page():
        ui.dark_mode(True)

        # ── Refs for dynamic update ──────────────────────────────
        video_grid_ref = None
        dl_table_ref = None
        console_ref = None
        status_ref = None
        cat_select_ref = None
        page_label_ref = None
        sel_badge_ref = None

        # ── Category loading ─────────────────────────────────────
        async def load_categories():
            nonlocal cat_select_ref
            browser = SITES[state.site_key]['browser']
            cats = await asyncio.to_thread(browser.fetch_categories)
            state.categories = cats
            if cat_select_ref:
                cat_select_ref.options = [c['name'] for c in cats]
                cat_select_ref.update()
            if cats:
                state.current_cat_idx = 0
                state.current_base_url = cats[0]['url']
                if cat_select_ref:
                    cat_select_ref.value = cats[0]['name']
                await load_page()

        # ── Page loading ─────────────────────────────────────────
        async def load_page():
            if state.loading:
                return
            state.loading = True
            refresh_video_grid()
            url = build_page_url(state)
            browser = SITES[state.site_key]['browser']
            try:
                videos = await asyncio.to_thread(browser.fetch_page, url)
            except Exception:
                videos = []
            state.videos = videos
            state.has_next = len(videos) >= 12
            state.loading = False
            refresh_video_grid()
            update_nav()

        # ── Video grid rendering ─────────────────────────────────
        def refresh_video_grid():
            nonlocal video_grid_ref
            if video_grid_ref is None:
                return
            video_grid_ref.clear()
            if state.loading:
                with video_grid_ref:
                    with ui.column().classes('w-full items-center py-20'):
                        ui.spinner('dots', size='xl', color=ACCENT)
                        ui.label('載入中...').classes('text-gray-400 mt-4')
                return
            if not state.videos:
                with video_grid_ref:
                    with ui.column().classes('w-full items-center py-20'):
                        ui.icon('search_off', size='xl', color='grey-7')
                        ui.label('沒有找到影片').classes('text-gray-400 mt-2')
                return
            with video_grid_ref:
                for v in state.videos:
                    build_video_card(v)

        def build_video_card(v: dict):
            url = v.get('url', '')
            is_sel = url in state.selected_urls
            sel_cls = ' selected' if is_sel else ''
            with ui.element('div').classes(f'video-card{sel_cls}').on(
                    'click', lambda _, u=url: toggle_select(u)):
                # Thumbnail
                thumb = v.get('thumbnail', '')
                dur = v.get('duration', '')
                with ui.element('div').classes('thumb-container'):
                    if thumb:
                        ui.element('img').props(f'src="{thumb}" loading="lazy"')
                    if dur:
                        ui.element('div').classes('duration-badge').text(dur)
                # Title
                title = v.get('title', '')
                ui.element('div').classes('card-title').text(
                    title[:80] + '…' if len(title) > 80 else title)

        def toggle_select(url: str):
            if url in state.selected_urls:
                state.selected_urls.discard(url)
            else:
                state.selected_urls.add(url)
            refresh_video_grid()
            update_sel_badge()

        def update_sel_badge():
            nonlocal sel_badge_ref
            n = len(state.selected_urls)
            if sel_badge_ref:
                sel_badge_ref.text = f'已選 {n} 部' if n else ''

        # ── Navigation ───────────────────────────────────────────
        def update_nav():
            nonlocal page_label_ref
            if page_label_ref:
                page_label_ref.text = f'第 {state.page} 頁'

        async def goto_page(p: int):
            if p < 1:
                return
            state.page = p
            await load_page()

        async def on_cat_change(e):
            idx = next((i for i, c in enumerate(state.categories)
                        if c['name'] == e.value), -1)
            if idx < 0:
                return
            state.current_cat_idx = idx
            state.current_base_url = state.categories[idx]['url']
            state.page = 1
            state.has_next = True
            state.selected_urls.clear()
            update_sel_badge()
            await load_page()

        async def on_search():
            q = state.search_query.strip()
            if not q:
                return
            if state.site_key == 'JableTV':
                state.current_base_url = f'https://jable.tv/search/?q={q}'
            else:
                state.current_base_url = f'https://missav.ai/dm265/cn/search?query={q}'
            state.page = 1
            state.has_next = True
            state.selected_urls.clear()
            update_sel_badge()
            await load_page()

        async def on_site_change(e):
            state.site_key = e.value
            state.categories.clear()
            state.selected_urls.clear()
            update_sel_badge()
            rebuild_sidebar()
            await load_categories()

        async def on_tag_click(url: str, name: str):
            state.current_base_url = url
            state.page = 1
            state.has_next = True
            state.selected_urls.clear()
            update_sel_badge()
            if cat_select_ref:
                cat_select_ref.value = f'🏷 {name}'
            await load_page()

        # ── Download actions ─────────────────────────────────────
        def add_selected_to_queue():
            for url in list(state.selected_urls):
                if M3U8Sites.VaildateUrl(url):
                    dlmgr.add_item(url, state='等待中')
            n = len(state.selected_urls)
            state.selected_urls.clear()
            update_sel_badge()
            refresh_video_grid()
            refresh_dl_table()
            ui.notify(f'已加入 {n} 部到清單', color=SUCCESS)

        def download_selected():
            dest = state.dest
            for url in list(state.selected_urls):
                if M3U8Sites.VaildateUrl(url):
                    dlmgr.add_item(url, state='等待中')
                    dlmgr.enqueue(url, dest)
            n = len(state.selected_urls)
            state.selected_urls.clear()
            update_sel_badge()
            refresh_video_grid()
            refresh_dl_table()
            ui.notify(f'{n} 部開始下載', color=ACCENT)

        def download_url_input():
            url = state.url_input.strip()
            if not url:
                ui.notify('請先輸入網址', color=WARNING)
                return
            if not M3U8Sites.VaildateUrl(url):
                ui.notify(f'不支援的網址', color=ERROR_C)
                return
            dlmgr.add_item(url, state='等待中')
            dlmgr.enqueue(url, state.dest)
            refresh_dl_table()
            ui.notify('已加入下載', color=SUCCESS)

        def download_all():
            dest = state.dest
            count = 0
            for item in dlmgr.get_items():
                if item.state not in ('已下載', '下載中', '準備中', '等待中'):
                    dlmgr.enqueue(item.url, dest)
                    count += 1
            refresh_dl_table()
            if count:
                ui.notify(f'已加入 {count} 個下載任務', color=SUCCESS)
            else:
                ui.notify('沒有需要下載的項目', color=WARNING)

        def cancel_all_downloads():
            dlmgr.cancel_all()
            refresh_dl_table()
            ui.notify('已取消所有下載', color=WARNING)

        def clear_queue():
            dlmgr.clear_all()
            refresh_dl_table()
            ui.notify('已清空下載清單', color=WARNING)

        def open_dest_folder():
            import subprocess, platform
            folder = os.path.abspath(state.dest)
            os.makedirs(folder, exist_ok=True)
            system = platform.system()
            if system == 'Windows':
                os.startfile(folder)
            elif system == 'Darwin':
                subprocess.Popen(['open', folder])
            else:
                subprocess.Popen(['xdg-open', folder])

        # ── Download table ───────────────────────────────────────
        def refresh_dl_table():
            nonlocal dl_table_ref
            if dl_table_ref is None:
                return
            dl_table_ref.clear()
            items = dlmgr.get_items()
            with dl_table_ref:
                if not items:
                    with ui.column().classes('w-full items-center py-8'):
                        ui.icon('download', size='xl', color='grey-8')
                        ui.label('下載清單是空的').classes('text-gray-500 mt-2')
                    return
                for item in items:
                    build_dl_row(item)

        def build_dl_row(item: DownloadItem):
            color_map = {
                '下載中': ACCENT, '準備中': ACCENT2, '等待中': WARNING,
                '已下載': SUCCESS, '未完成': WARNING, '已取消': '#666688',
                '網址錯誤': ERROR_C,
            }
            color = color_map.get(item.state, '#a0a0c0')
            with ui.row().classes(
                    'w-full items-center px-4 py-2 gap-4'
                    ).style('background: #161630; border-bottom: 1px solid #222240;'
                            'min-height: 44px;'):
                # Status chip
                ui.badge(item.state or '—', color=color).classes(
                    'status-chip').style('min-width: 60px; text-align: center;')
                # Name
                ui.label(item.name).classes(
                    'text-sm flex-grow truncate'
                    ).style('color: #f0f0f8; max-width: 400px;')
                # Progress bar
                if item.state == '下載中' and item.progress > 0:
                    ui.linear_progress(
                        value=item.progress / 100, show_value=False
                    ).props('color="red-8" track-color="grey-9"').classes(
                        'flex-grow').style('max-width: 200px;')
                    ui.label(f'{item.progress}%').classes(
                        'text-xs').style('color: #a0a0c0; width: 40px;')
                else:
                    ui.element('div').classes('flex-grow')
                # Speed
                if item.speed:
                    ui.label(item.speed).classes(
                        'text-xs').style('color: #a0a0c0; width: 80px;')
                # Delete button
                ui.button(icon='close', on_click=lambda _, u=item.url:
                          (dlmgr.remove_item(u), refresh_dl_table())
                          ).props('flat dense round size="sm" color="grey-7"')

        # ── Speed limiter ────────────────────────────────────────
        def on_speed_change(e):
            from M3U8Sites.M3U8Crawler import speed_limiter
            val = e.value
            if val == '無限制':
                speed_limiter.set_limit(0)
            else:
                mbps = float(val.split()[0])
                speed_limiter.set_limit(mbps)
            ui.notify(f'速度限制: {val}', color='info')

        # ── Sidebar builder ──────────────────────────────────────
        sidebar_container_ref = None

        def rebuild_sidebar():
            nonlocal sidebar_container_ref
            if sidebar_container_ref is None:
                return
            sidebar_container_ref.clear()
            with sidebar_container_ref:
                if state.site_key == 'JableTV':
                    build_jable_sidebar()
                else:
                    with ui.column().classes('w-full items-center py-8'):
                        ui.label('僅 JableTV 支援標籤瀏覽').classes(
                            'text-gray-600 text-sm')

        def build_jable_sidebar():
            tags = JableTVBrowser.SIDEBAR_TAGS
            for group_name, tag_list in tags.items():
                expanded = state.sidebar_expanded.get(group_name, False)
                # Group header
                with ui.element('div').classes('group-header').on(
                        'click', lambda _, g=group_name: toggle_sidebar_group(g)):
                    arrow = '▾' if expanded else '▸'
                    ui.label(arrow).style(
                        'color: #666688; font-size: 11px; width: 12px;')
                    ui.label(group_name).style(
                        'color: #a0a0c0; font-size: 13px; font-weight: bold;'
                        'flex-grow: 1;')
                    ui.label(str(len(tag_list))).style(
                        'color: #666688; font-size: 11px;')
                # Tag list (visible if expanded)
                if expanded:
                    for name, slug in tag_list:
                        tag_url = JableTVBrowser.tag_url(slug)
                        ui.element('div').classes('tag-btn').text(name).on(
                            'click', lambda _, u=tag_url, n=name:
                            on_tag_click(u, n))

        def toggle_sidebar_group(group_name: str):
            state.sidebar_expanded[group_name] = not state.sidebar_expanded.get(
                group_name, False)
            rebuild_sidebar()

        # ── Auto-refresh download table ──────────────────────────
        dl_timer = None

        def start_dl_refresh():
            nonlocal dl_timer
            refresh_dl_table()
            dl_timer = ui.timer(2.0, refresh_dl_table)

        # ── Layout ───────────────────────────────────────────────
        with ui.header().classes('items-center px-4 py-2 gap-4'):
            ui.label('JableTV & MissAV Downloader').classes(
                'text-lg font-bold').style(f'color: {ACCENT};')
            ui.space()
            ui.label('v2.0 Modern UI').classes('text-xs').style(
                'color: #666688;')

        with ui.left_drawer(value=True, bordered=True).classes(
                'px-0 py-0').style(
                'width: 200px; background: #0a0a16;') as drawer:
            # Sidebar header
            with ui.element('div').style(
                    'background: #0e0e20; padding: 12px 14px;'):
                ui.label('標籤選片').style(
                    f'color: {ACCENT}; font-size: 14px; font-weight: bold;')
            ui.separator().style('background: #2a2a48;')
            sidebar_container_ref = ui.column().classes('w-full gap-0')

        with ui.column().classes('w-full h-full gap-0'):
            # ── Tabs ─────────────────────────────────────────────
            with ui.tabs().classes('w-full').props(
                    'dense align="left" active-color="red-8"'
                    ' indicator-color="red-8"'
                    ).style('background: #101020;') as tabs:
                browse_tab = ui.tab('瀏覽', icon='explore')
                dl_tab = ui.tab('下載', icon='download')
                settings_tab = ui.tab('設定', icon='settings')

            with ui.tab_panels(tabs, value='瀏覽').classes('w-full flex-grow'):

                # ══════════════════════════════════════════════════
                #  Browse tab
                # ══════════════════════════════════════════════════
                with ui.tab_panel('瀏覽').classes('p-0'):
                    # Top bar
                    with ui.row().classes(
                            'w-full items-center px-4 py-2 gap-3'
                            ).style('background: #101020;'):
                        # Site selector
                        ui.select(
                            list(SITES.keys()), value='JableTV',
                            label='站點', on_change=on_site_change
                        ).props('dense outlined dark').classes('w-28')
                        ui.separator().props('vertical')

                        # Category selector
                        cat_select_ref = ui.select(
                            [], label='分類', on_change=on_cat_change
                        ).props('dense outlined dark').classes('w-40')

                        ui.separator().props('vertical')

                        # Search
                        ui.input(
                            placeholder='搜尋影片...',
                            on_change=lambda e: setattr(state, 'search_query', e.value)
                        ).props('dense outlined dark').classes('w-52').on(
                            'keydown.enter', on_search)
                        ui.button('搜尋', on_click=on_search, color='red-8'
                                  ).props('dense unelevated')

                        ui.space()

                        # Selection controls
                        sel_badge_ref = ui.label('').style(
                            f'color: {ACCENT}; font-weight: bold; font-size: 13px;')
                        ui.button('加入清單', on_click=add_selected_to_queue
                                  ).props('flat dense color="grey-5"')
                        ui.button('下載選中', on_click=download_selected,
                                  color='red-8').props('dense unelevated')

                    ui.separator().style('background: #222240;')

                    # Video grid
                    video_grid_ref = ui.element('div').classes(
                        'w-full px-4 py-4'
                    ).style(
                        'display: grid;'
                        'grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));'
                        'gap: 12px;'
                        'overflow-y: auto; flex-grow: 1;'
                    )

                    # Bottom nav
                    ui.separator().style('background: #222240;')
                    with ui.row().classes(
                            'w-full items-center justify-center px-4 py-3 gap-4'
                            ).style('background: #101020;'):
                        ui.button('« 首頁', on_click=lambda: goto_page(1)
                                  ).props('flat dense color="grey-5"')
                        ui.button('‹ 上一頁',
                                  on_click=lambda: goto_page(state.page - 1)
                                  ).props('flat dense color="grey-5"')
                        page_label_ref = ui.label('第 1 頁').style(
                            'color: #f0f0f8; font-weight: bold;'
                            'min-width: 80px; text-align: center;')
                        ui.button('下一頁 ›',
                                  on_click=lambda: goto_page(state.page + 1),
                                  color='red-8').props('dense unelevated')

                # ══════════════════════════════════════════════════
                #  Download tab
                # ══════════════════════════════════════════════════
                with ui.tab_panel('下載').classes('p-0'):
                    # URL input section
                    with ui.row().classes(
                            'w-full items-center px-4 py-3 gap-3'
                            ).style('background: #131328;'):
                        ui.input(
                            label='存放位置', value=state.dest,
                            on_change=lambda e: setattr(state, 'dest', e.value)
                        ).props('dense outlined dark').classes('flex-grow')
                        ui.button(icon='folder_open', on_click=open_dest_folder
                                  ).props('flat dense color="grey-5"')

                    with ui.row().classes(
                            'w-full items-center px-4 py-2 gap-3'
                            ).style('background: #131328;'):
                        ui.input(
                            label='下載網址',
                            on_change=lambda e: setattr(state, 'url_input', e.value)
                        ).props('dense outlined dark').classes('flex-grow')

                    # Action bar
                    ui.separator().style('background: #222240;')
                    with ui.row().classes(
                            'w-full items-center px-4 py-2 gap-2 flex-wrap'
                            ).style('background: #101020;'):
                        ui.button('▶ 下載', on_click=download_url_input,
                                  color='red-8').props('dense unelevated')
                        ui.button('▶▶ 全部下載', on_click=download_all,
                                  color='red-8').props('dense unelevated')
                        ui.separator().props('vertical').classes('mx-2')
                        ui.button('清空清單', on_click=clear_queue
                                  ).props('flat dense color="red-4"')
                        ui.button('全部取消', on_click=cancel_all_downloads
                                  ).props('flat dense color="red-4"')

                        ui.space()
                        ui.label('速度限制:').style('color: #a0a0c0; font-size: 12px;')
                        ui.select(
                            ['無限制', '1 MB/s', '2 MB/s', '5 MB/s',
                             '10 MB/s', '15 MB/s'],
                            value='無限制', on_change=on_speed_change
                        ).props('dense outlined dark').classes('w-28')

                    # Download list
                    ui.separator().style('background: #222240;')
                    dl_table_ref = ui.column().classes('w-full gap-0 flex-grow'
                                                       ).style('overflow-y: auto;')

                # ══════════════════════════════════════════════════
                #  Settings tab
                # ══════════════════════════════════════════════════
                with ui.tab_panel('設定').classes('p-6'):
                    with ui.card().classes('w-full max-w-2xl mx-auto').style(
                            'background: #131328;'):
                        ui.label('設定').classes('text-xl font-bold mb-4'
                                                ).style('color: #f0f0f8;')

                        with ui.column().classes('w-full gap-4'):
                            ui.label('下載設定').classes('text-sm font-bold'
                                                        ).style('color: #a0a0c0;')
                            ui.input(
                                label='存放位置', value=state.dest,
                                on_change=lambda e: setattr(state, 'dest', e.value)
                            ).props('outlined dark').classes('w-full')

                            ui.select(
                                ['無限制', '1 MB/s', '2 MB/s', '5 MB/s',
                                 '10 MB/s', '15 MB/s'],
                                value='無限制', label='速度限制',
                                on_change=on_speed_change
                            ).props('outlined dark').classes('w-48')

                            with ui.row().classes('items-center gap-2'):
                                ui.label('同時下載數:').style(
                                    'color: #a0a0c0; font-size: 13px;')
                                ui.label(str(MAX_CONCURRENT)).style(
                                    'color: #f0f0f8;')
                                ui.label('(固定)').style(
                                    'color: #666688; font-size: 12px;')

                        ui.separator().classes('my-4').style('background: #222240;')

                        with ui.column().classes('w-full gap-2'):
                            ui.label('關於').classes('text-sm font-bold'
                                                    ).style('color: #a0a0c0;')
                            ui.label('JableTV & MissAV Downloader').style(
                                'color: #f0f0f8;')
                            ui.label(
                                'v2.0.0 Modern UI  •  僅供學習與研究用途'
                            ).style('color: #a0a0c0; font-size: 12px;')

        # ── Footer ───────────────────────────────────────────────
        with ui.footer().classes('items-center px-4 py-1'):
            status_ref = ui.label('就緒').style(
                'color: #a0a0c0; font-size: 12px;')

        # ── On page load ─────────────────────────────────────────
        rebuild_sidebar()
        await load_categories()
        start_dl_refresh()

    # ── Save on shutdown ─────────────────────────────────────────
    app.on_shutdown(lambda: dlmgr.save_csv(CSV_PATH))

    ui.run(
        title='JableTV & MissAV Downloader',
        port=8088,
        reload=False,
        show=True,
        dark=True,
        favicon='🎬',
    )
