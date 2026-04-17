#!/usr/bin/env python
# coding: utf-8
"""Jable SmallTool — auto-downloader for new 中文字幕 videos.

Watches the jable.tv/tags/chinese-subtitle/ page daily and downloads any
new video it hasn't seen before. Keeps running in the background; the user
only needs to pick an output folder once, then minimize the window.

Author: ALOS
"""

import ctypes
import json
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, scrolledtext
from typing import Optional

# Enable DPI awareness (Windows)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import M3U8Sites
from M3U8Sites.SiteJableTV import JableTVBrowser

# Optional direct-fetch fallback for diagnostics / when cloudscraper struggles
try:
    import cloudscraper
    from bs4 import BeautifulSoup
except Exception:
    cloudscraper = None
    BeautifulSoup = None

# ── Constants ────────────────────────────────────────────────────────
APP_NAME = 'Jable_smalltool'
TAG_SLUG = 'chinese-subtitle'
TAG_URL = f'https://jable.tv/tags/{TAG_SLUG}/'
BASELINE_DATE = '2026-04-01'
CHECK_INTERVAL_SEC = 24 * 60 * 60  # 24 hours
MAX_SCAN_PAGES = 50                # safety cap to avoid infinite scanning
DAILY_SCAN_PAGES = 3               # a bit of overlap in case of late uploads
MAX_CONCURRENT = 2

# State files live next to the exe for portability
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(APP_DIR, f'.{APP_NAME}')
CONFIG_PATH = os.path.join(STATE_DIR, 'config.json')
SEEN_PATH = os.path.join(STATE_DIR, 'seen.json')

# Palette (align with main app)
BG_DARK = '#0d0d18'
BG_CARD = '#161630'
BG_INPUT = '#1c1c38'
BG_HEADER = '#101020'
ACCENT = '#e94560'
ACCENT_HOVER = '#c73350'
SUCCESS = '#4ade80'
WARNING = '#fbbf24'
ERROR_C = '#f87171'
TEXT_PRI = '#f0f0f8'
TEXT_SEC = '#a0a0c0'
TEXT_DIM = '#666688'
BORDER = '#2a2a48'


# ── Persistence ──────────────────────────────────────────────────────
def _ensure_state_dir() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)


def load_config() -> dict:
    _ensure_state_dir()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'output_folder': '',
        'baseline_date': BASELINE_DATE,
        'first_run_done': False,
    }


def save_config(cfg: dict) -> None:
    _ensure_state_dir()
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_seen() -> dict:
    _ensure_state_dir()
    if os.path.exists(SEEN_PATH):
        try:
            with open(SEEN_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_seen(seen: dict) -> None:
    _ensure_state_dir()
    with open(SEEN_PATH, 'w', encoding='utf-8') as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)


# ── Downloader core ──────────────────────────────────────────────────
class SmallToolWorker:
    """Background worker that scans the tag page daily and downloads new videos.

    One-at-a-time download semantics keep it gentle on bandwidth and simple
    to reason about (no progress UI per-file needed). If the user configures
    a larger concurrency we still cap at MAX_CONCURRENT.
    """

    def __init__(self, log_fn):
        self._log = log_fn
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen = load_seen()
        self._seen_lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Main loop ────────────────────────────────────────────────────
    def _run(self):
        cfg = load_config()
        self._log('Worker started.')
        while not self._stop.is_set():
            try:
                self._scan_and_download(cfg)
            except Exception as e:
                self._log(f'[ERROR] scan failed: {e}')
            cfg = load_config()   # re-read in case user changed folder
            # Sleep in 5s slices so stop() reacts quickly
            waited = 0
            while waited < CHECK_INTERVAL_SEC and not self._stop.is_set():
                time.sleep(5)
                waited += 5
        self._log('Worker stopped.')

    def _verbose_fetch_page(self, url: str) -> list:
        """Like JableTVBrowser.fetch_page but logs exactly why it returns empty.
        Helps diagnose Cloudflare challenges, site structure changes, etc."""
        if cloudscraper is None or BeautifulSoup is None:
            # Fall back to JableTVBrowser without diagnostics
            try:
                return JableTVBrowser.fetch_page(url)
            except Exception as e:
                self._log(f'  [ERR] fetch failed: {e}')
                return []
        try:
            scraper = JableTVBrowser._get_scraper()
            r = scraper.get(url, timeout=30)
        except Exception as e:
            self._log(f'  [ERR] HTTP request failed: {type(e).__name__}: {e}')
            return []

        self._log(f'  HTTP {r.status_code}, body={len(r.content)} bytes')
        if r.status_code != 200:
            snippet = (r.text or '')[:200].replace('\n', ' ')
            self._log(f'  Body snippet: {snippet}')
            return []

        try:
            soup = BeautifulSoup(r.content, 'html.parser')
        except Exception as e:
            self._log(f'  [ERR] HTML parse failed: {e}')
            return []

        divlist = soup.find('div', id=lambda x: x and x.startswith('list_videos'))
        if divlist is None:
            # Check for Cloudflare challenge indicators
            title = soup.title.string if soup.title else ''
            has_cf = ('cloudflare' in r.text.lower() or
                      'just a moment' in r.text.lower() or
                      'challenge' in r.text.lower())
            self._log(
                f'  [WARN] list_videos div not found. '
                f'title="{title}" cloudflare_indicators={has_cf}'
            )
            return []

        cards = divlist.select('div.video-img-box')
        videos = []
        for card in cards:
            detail = card.select_one('div.detail')
            if not detail or not detail.h6 or not detail.h6.a:
                continue
            tag_a = detail.h6.a
            img = card.select_one('img')
            duration_span = card.select_one('span.label')
            videos.append({
                'url': tag_a.get('href', ''),
                'title': str(tag_a.string or ''),
                'thumbnail': img.get('data-src', '') if img else '',
                'duration': duration_span.string if duration_span else '',
            })
        return videos

    def _scan_and_download(self, cfg: dict):
        dest = cfg.get('output_folder') or ''
        if not dest:
            self._log('[WAIT] No output folder configured.')
            return
        os.makedirs(dest, exist_ok=True)

        first_run = not cfg.get('first_run_done', False)

        if first_run:
            self._log(
                f'First run — scanning ALL 中文字幕 pages since {BASELINE_DATE}...'
            )
        else:
            self._log(
                f'Daily check — scanning up to {DAILY_SCAN_PAGES} page(s) of 中文字幕...'
            )

        new_videos = []
        max_pages = MAX_SCAN_PAGES if first_run else DAILY_SCAN_PAGES

        for page in range(1, max_pages + 1):
            if self._stop.is_set():
                return
            url = TAG_URL if page == 1 else f'{TAG_URL}?from={page}'
            self._log(f'Fetching page {page}: {url}')
            try:
                videos = self._verbose_fetch_page(url)
            except Exception as e:
                self._log(f'[WARN] page {page} fetch failed: {e}')
                continue
            if not videos:
                self._log(f'Page {page}: no videos returned — reached end.')
                break

            self._log(f'Page {page}: got {len(videos)} video(s).')
            page_all_seen = True
            for v in videos:
                vurl = v.get('url', '')
                if not vurl:
                    continue
                with self._seen_lock:
                    if vurl in self._seen:
                        continue
                page_all_seen = False
                new_videos.append(v)

            # Daily mode: stop if all videos on this page are already seen
            if not first_run and page_all_seen:
                self._log('All videos on this page already seen — stopping.')
                break

        if not new_videos:
            self._log('No new videos found.')
            cfg['first_run_done'] = True
            save_config(cfg)
            return

        self._log(f'Found {len(new_videos)} new video(s). Starting downloads...')
        for v in new_videos:
            if self._stop.is_set():
                return
            self._download_one(v, dest)

        cfg['first_run_done'] = True
        cfg['last_check_iso'] = datetime.now(timezone.utc).isoformat()
        save_config(cfg)

    def _download_one(self, video: dict, dest: str):
        vurl = video['url']
        title = video.get('title', '') or vurl.rstrip('/').split('/')[-1]
        self._log(f'↓ {title}')
        try:
            site = M3U8Sites.CreateSite(vurl, dest)
            if not site or not site.is_url_vaildate():
                self._log(f'  [SKIP] invalid URL: {vurl}')
                self._mark_seen(vurl, title, skipped=True)
                return
            site.start_download()
            if getattr(site, '_cancel_job', False):
                self._log('  [CANCELLED]')
                return
            self._log(f'  [OK] {title}')
            self._mark_seen(vurl, title)
        except Exception as e:
            self._log(f'  [ERR] {e}')
            # Don't mark seen; will retry next cycle

    def _mark_seen(self, url: str, title: str, skipped: bool = False):
        with self._seen_lock:
            self._seen[url] = {
                'title': title,
                'at': datetime.now(timezone.utc).isoformat(),
                'skipped': skipped,
            }
            save_seen(self._seen)


# ── GUI ──────────────────────────────────────────────────────────────
class SmallToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'{APP_NAME} — Jable 中文字幕 每日下載 — by ALOS')
        self.geometry('720x480')
        self.minsize(600, 400)
        self.configure(bg=BG_DARK)

        self._cfg = load_config()
        self._log_queue: list[str] = []
        self._log_lock = threading.Lock()
        self._worker = SmallToolWorker(log_fn=self._enqueue_log)

        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        # Auto-start if an output folder is already configured
        if self._cfg.get('output_folder'):
            self._start_worker()

        # Drain log queue onto the Tk main loop
        self.after(300, self._flush_log_queue)

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG_HEADER, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text='Jable 小工具 — 中文字幕 每日自動下載',
                 bg=BG_HEADER, fg=ACCENT,
                 font=('Microsoft YaHei', 13, 'bold')).pack(
            side='left', padx=14)
        tk.Label(hdr, text='by ALOS',
                 bg=BG_HEADER, fg=TEXT_DIM,
                 font=('Microsoft YaHei', 10)).pack(side='right', padx=14)

        # Config area
        cfg_frame = tk.Frame(self, bg=BG_DARK)
        cfg_frame.pack(fill='x', padx=14, pady=(10, 6))

        tk.Label(cfg_frame, text='儲存位置:', bg=BG_DARK, fg=TEXT_SEC,
                 font=('Microsoft YaHei', 10)).pack(side='left')
        self._folder_var = tk.StringVar(value=self._cfg.get('output_folder', ''))
        entry = tk.Entry(cfg_frame, textvariable=self._folder_var,
                         bg=BG_INPUT, fg=TEXT_PRI,
                         insertbackground=TEXT_PRI,
                         relief='flat', bd=4,
                         font=('Microsoft YaHei', 10))
        entry.pack(side='left', fill='x', expand=True, padx=8)
        tk.Button(cfg_frame, text='選擇資料夾',
                  bg=BG_CARD, fg=TEXT_PRI,
                  activebackground='#2a2a4a',
                  relief='flat', bd=0, padx=10, pady=4,
                  command=self._pick_folder).pack(side='left')

        # Control row
        ctrl = tk.Frame(self, bg=BG_DARK)
        ctrl.pack(fill='x', padx=14, pady=(0, 6))

        self._start_btn = tk.Button(
            ctrl, text='▶ 啟動背景偵測',
            bg=ACCENT, fg='#ffffff',
            activebackground=ACCENT_HOVER,
            relief='flat', bd=0, padx=14, pady=6,
            font=('Microsoft YaHei', 10, 'bold'),
            command=self._start_worker)
        self._start_btn.pack(side='left')

        self._stop_btn = tk.Button(
            ctrl, text='■ 停止',
            bg='#3a1a20', fg=ERROR_C,
            activebackground='#2a1215',
            relief='flat', bd=0, padx=14, pady=6,
            font=('Microsoft YaHei', 10),
            command=self._stop_worker,
            state='disabled')
        self._stop_btn.pack(side='left', padx=(8, 0))

        self._check_now_btn = tk.Button(
            ctrl, text='↻ 立即檢查一次',
            bg=BG_CARD, fg=TEXT_PRI,
            activebackground='#2a2a4a',
            relief='flat', bd=0, padx=14, pady=6,
            font=('Microsoft YaHei', 10),
            command=self._check_now)
        self._check_now_btn.pack(side='left', padx=(8, 0))

        self._status_lbl = tk.Label(
            ctrl, text='閒置', bg=BG_DARK, fg=TEXT_DIM,
            font=('Microsoft YaHei', 10))
        self._status_lbl.pack(side='right')

        # Info line
        info = tk.Label(
            self,
            text=(f'監看標籤: 中文字幕 ({TAG_URL})   |   '
                  f'每 24 小時自動檢查一次   |   '
                  f'基準日期: {BASELINE_DATE}'),
            bg=BG_DARK, fg=TEXT_DIM, font=('Microsoft YaHei', 9),
            anchor='w')
        info.pack(fill='x', padx=14, pady=(0, 8))

        # Log box
        self._log_box = scrolledtext.ScrolledText(
            self, bg=BG_CARD, fg=TEXT_PRI,
            insertbackground=TEXT_PRI,
            relief='flat', bd=0,
            font=('Consolas', 10),
            wrap='word', state='disabled')
        self._log_box.pack(fill='both', expand=True, padx=14, pady=(0, 10))

        # Footer
        footer = tk.Label(
            self,
            text='提示：關閉視窗會結束程式。最小化後程式仍在背景運行。',
            bg=BG_DARK, fg=TEXT_DIM, font=('Microsoft YaHei', 9))
        footer.pack(pady=(0, 8))

    # ── Handlers ─────────────────────────────────────────────────────
    def _pick_folder(self):
        d = filedialog.askdirectory(title='選擇影片儲存資料夾')
        if d:
            self._folder_var.set(d)
            self._cfg['output_folder'] = d
            save_config(self._cfg)
            self._log(f'儲存位置已設為 {d}')

    def _start_worker(self):
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning('缺少資料夾', '請先選擇影片儲存資料夾。')
            return
        # Persist chosen folder so next launch starts automatically
        self._cfg['output_folder'] = folder
        save_config(self._cfg)

        self._worker.start()
        self._start_btn.configure(state='disabled')
        self._stop_btn.configure(state='normal')
        self._status_lbl.configure(text='● 執行中', fg=SUCCESS)
        self._log('背景偵測已啟動 — 你可以將視窗最小化。')

    def _stop_worker(self):
        self._worker.stop()
        self._start_btn.configure(state='normal')
        self._stop_btn.configure(state='disabled')
        self._status_lbl.configure(text='已停止', fg=TEXT_DIM)

    def _check_now(self):
        """Trigger an immediate scan by bumping the worker — if not running,
        kick off a one-shot scan in a thread."""
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning('缺少資料夾', '請先選擇影片儲存資料夾。')
            return
        self._cfg['output_folder'] = folder
        save_config(self._cfg)

        def _once():
            cfg = load_config()
            try:
                self._worker._scan_and_download(cfg)
            except Exception as e:
                self._log(f'[ERR] {e}')

        threading.Thread(target=_once, daemon=True).start()
        self._log('立即檢查中...')

    # ── Logging (thread-safe) ────────────────────────────────────────
    def _enqueue_log(self, msg: str):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        with self._log_lock:
            self._log_queue.append(line)

    def _log(self, msg: str):
        self._enqueue_log(msg)

    def _flush_log_queue(self):
        with self._log_lock:
            pending = self._log_queue[:]
            self._log_queue.clear()
        if pending:
            self._log_box.configure(state='normal')
            for line in pending:
                self._log_box.insert('end', line + '\n')
            self._log_box.see('end')
            self._log_box.configure(state='disabled')
        self.after(300, self._flush_log_queue)

    def _on_close(self):
        self._worker.stop()
        try:
            save_config(self._cfg)
        except Exception:
            pass
        self.destroy()


def main():
    app = SmallToolApp()
    app.mainloop()


if __name__ == '__main__':
    main()
