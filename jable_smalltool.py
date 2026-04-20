#!/usr/bin/env python
# coding: utf-8
"""Jable SmallTool — auto-downloader with site/category/date selection.

Supports JableTV and MissAV. The user picks which sites, which categories
(multi-select), and a baseline date. The worker scans selected categories
daily and downloads any new video it hasn't seen before.

Author: ALOS
"""

import ctypes
import json
import os
import shutil
import sys
import threading
import time
import tkinter as tk
import tkinter.ttk as ttk
import re
from datetime import datetime, timezone, timedelta
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
from M3U8Sites.SiteMissAV import MissAVBrowser

# Optional direct-fetch fallback for diagnostics / when cloudscraper struggles
try:
    import cloudscraper
    from bs4 import BeautifulSoup
except Exception:
    cloudscraper = None
    BeautifulSoup = None

# ── Constants ────────────────────────────────────────────────────────
APP_NAME = 'Jable_smalltool'
_yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
DEFAULT_BASELINE_DATE = _yesterday.strftime('%Y-%m-%d')
DEFAULT_BASELINE_DT = datetime(_yesterday.year, _yesterday.month, _yesterday.day, tzinfo=timezone.utc)
PER_VIDEO_FETCH_DELAY_SEC = 0.3
CHECK_INTERVAL_SEC = 24 * 60 * 60  # 24 hours
MAX_SCAN_PAGES = 50
DAILY_SCAN_PAGES = 3
MAX_CONCURRENT = 2

# ── Site / category registry ────────────────────────────────────────
# Each site entry: (display_name, browser_class, categories_list)
# categories_list: [(cat_name, cat_url), ...]

JABLE_CATEGORIES = [
    ('最近更新', 'https://jable.tv/latest-updates/'),
    ('熱門影片', 'https://jable.tv/hot/'),
    ('新片上架', 'https://jable.tv/new-release/'),
    ('中文字幕', 'https://jable.tv/categories/chinese-subtitle/'),
]

MISSAV_CATEGORIES = [
    ('今日熱門', 'https://missav.ai/dm291/today-hot'),
    ('本週熱門', 'https://missav.ai/dm169/weekly-hot'),
    ('本月熱門', 'https://missav.ai/dm263/monthly-hot'),
    ('中文字幕', 'https://missav.ai/dm265/chinese-subtitle'),
    ('最近更新', 'https://missav.ai/dm515/new'),
    ('新作上市', 'https://missav.ai/dm590/release'),
    ('無碼流出', 'https://missav.ai/dm628/uncensored-leak'),
    ('FC2', 'https://missav.ai/dm150/fc2'),
    ('麻豆傳媒', 'https://missav.ai/dm35/madou'),
]

SITES = {
    'JableTV': {
        'browser': JableTVBrowser,
        'categories': JABLE_CATEGORIES,
    },
    'MissAV': {
        'browser': MissAVBrowser,
        'categories': MISSAV_CATEGORIES,
    },
}

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
CHECK_ON = '#e94560'
CHECK_OFF = '#2a2a48'


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
        'baseline_date': DEFAULT_BASELINE_DATE,
        'first_run_done': False,
        'selected_targets': [],  # list of {"site": "JableTV", "category": "中文字幕"}
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
    """Background worker that scans selected site/category combos and downloads new videos."""

    def __init__(self, log_fn):
        self._log = log_fn
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen = load_seen()
        self._seen_lock = threading.Lock()
        self._progress = None  # (done, total, speed_bps, title) or None
        self._progress_lock = threading.Lock()

    def get_progress(self):
        with self._progress_lock:
            return self._progress

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
            cfg = load_config()
            waited = 0
            while waited < CHECK_INTERVAL_SEC and not self._stop.is_set():
                time.sleep(5)
                waited += 5
        self._log('Worker stopped.')

    # Chinese numerals → int
    _CN_NUMS = {
        '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    }

    @classmethod
    def _parse_cn_number(cls, s: str) -> Optional[int]:
        if not s:
            return None
        if '十' in s:
            parts = s.split('十')
            left = parts[0]
            right = parts[1] if len(parts) > 1 else ''
            tens = cls._CN_NUMS.get(left, 1) if left else 1
            ones = cls._CN_NUMS.get(right, 0) if right else 0
            return tens * 10 + ones
        if len(s) == 1 and s in cls._CN_NUMS:
            return cls._CN_NUMS[s]
        return None

    @classmethod
    def _parse_relative_date(cls, rel_text: str, now: Optional[datetime] = None) -> Optional[datetime]:
        if not rel_text:
            return None
        if now is None:
            now = datetime.now(timezone.utc)
        m = re.match(
            r'\s*(\d+|[一二兩三四五六七八九十]+)'
            r'\s*(個)?\s*'
            r'(分鐘|小時|天|星期|週|周|個?月|個?年)\s*前',
            rel_text,
        )
        if not m:
            return None
        num_raw = m.group(1)
        if num_raw.isdigit():
            n = int(num_raw)
        else:
            n = cls._parse_cn_number(num_raw)
            if n is None:
                return None
        unit = m.group(3)
        if unit == '分鐘':
            delta = timedelta(minutes=n)
        elif unit == '小時':
            delta = timedelta(hours=n)
        elif unit == '天':
            delta = timedelta(days=n)
        elif unit in ('星期', '週', '周'):
            delta = timedelta(weeks=n)
        elif unit in ('月', '個月'):
            delta = timedelta(days=n * 30)
        elif unit in ('年', '個年'):
            delta = timedelta(days=n * 365)
        else:
            return None
        return now - delta

    def _fetch_video_date(self, vurl: str) -> tuple[Optional[datetime], str]:
        """Fetch a video detail page and extract its post datetime (JableTV only)."""
        if cloudscraper is None or BeautifulSoup is None:
            return (None, '')
        try:
            scraper = JableTVBrowser._get_scraper()
            r = scraper.get(vurl, timeout=30)
            if r.status_code != 200:
                return (None, f'HTTP {r.status_code}')
            soup = BeautifulSoup(r.content, 'html.parser')
            info = soup.find(class_='info-header')
            if not info:
                return (None, '')
            span = info.find('span', class_='mr-3')
            if not span:
                return (None, '')
            rel_text = span.get_text(strip=True)
            return (self._parse_relative_date(rel_text), rel_text)
        except Exception as e:
            return (None, f'ERR:{type(e).__name__}')

    def _fetch_missav_video_date(self, vurl: str) -> tuple[Optional[datetime], str]:
        """Fetch a MissAV video page and extract its release date."""
        if cloudscraper is None or BeautifulSoup is None:
            return (None, '')
        try:
            scraper = MissAVBrowser._get_scraper()
            r = scraper.get(vurl, timeout=30)
            if r.status_code != 200:
                return (None, f'HTTP {r.status_code}')

            soup = BeautifulSoup(r.content, 'html.parser')
            page_text = soup.get_text(' ', strip=True)

            # Method 1: date near known keywords (発売日, Release Date, etc.)
            for pat in [
                r'(?:発売日|發售日|配信開始日|Release\s*Date|上架日期|更新)\s*[:：]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
                r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*(?:発売|release|上架)',
            ]:
                m = re.search(pat, page_text, re.I)
                if m:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
                        return (datetime(y, mo, d, tzinfo=timezone.utc),
                                f'{y}-{mo:02d}-{d:02d}')

            # Method 2: meta tags (og / video release_date)
            for meta in soup.find_all('meta'):
                prop = (meta.get('property') or meta.get('name') or '').lower()
                if any(k in prop for k in ('release', 'date', 'published')):
                    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', meta.get('content', ''))
                    if m:
                        return (datetime(int(m.group(1)), int(m.group(2)),
                                         int(m.group(3)), tzinfo=timezone.utc),
                                m.group(0))

            # Method 3: <time> element
            time_el = soup.find('time', attrs={'datetime': True})
            if time_el:
                m = re.match(r'(\d{4})-(\d{2})-(\d{2})', time_el['datetime'])
                if m:
                    return (datetime(int(m.group(1)), int(m.group(2)),
                                     int(m.group(3)), tzinfo=timezone.utc),
                            m.group(0))

            return (None, '')
        except Exception as e:
            return (None, f'ERR:{type(e).__name__}')

    def _fetch_page_for_site(self, site_name: str, url: str) -> list:
        """Fetch a listing page using the appropriate browser for the site."""
        browser = SITES[site_name]['browser']
        try:
            return browser.fetch_page(url)
        except Exception as e:
            self._log(f'  [ERR] fetch failed: {e}')
            return []

    def _build_page_url(self, site_name: str, base_url: str, page: int) -> str:
        """Build paginated URL for the given site."""
        if page <= 1:
            return base_url
        if site_name == 'JableTV':
            # JableTV uses ?sort_by=post_date&from=N
            if '?' in base_url:
                return f'{base_url}&from={page}'
            return f'{base_url}?from={page}'
        else:
            # MissAV uses ?page=N
            sep = '&' if '?' in base_url else '?'
            return f'{base_url}{sep}page={page}'

    def _scan_and_download(self, cfg: dict):
        dest = cfg.get('output_folder') or ''
        if not dest:
            self._log('[WAIT] No output folder configured.')
            return
        os.makedirs(dest, exist_ok=True)

        targets = cfg.get('selected_targets', [])
        if not targets:
            self._log('[WAIT] No sites/categories selected.')
            return

        baseline_str = cfg.get('baseline_date', DEFAULT_BASELINE_DATE)
        try:
            baseline_dt = datetime.strptime(baseline_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            baseline_dt = DEFAULT_BASELINE_DT

        first_run = not cfg.get('first_run_done', False)
        is_jable_site = any(t['site'] == 'JableTV' for t in targets)

        self._log(f'{"First run" if first_run else "Daily check"} — '
                  f'{len(targets)} target(s), baseline {baseline_str}')

        all_new_videos = []

        for target in targets:
            if self._stop.is_set():
                return
            site_name = target['site']
            cat_name = target['category']

            # Find the URL for this category
            cat_url = None
            for name, url in SITES[site_name]['categories']:
                if name == cat_name:
                    cat_url = url
                    break
            if not cat_url:
                self._log(f'[WARN] category not found: {site_name}/{cat_name}')
                continue

            self._log(f'── {site_name} / {cat_name} ──')

            # Add sort param for JableTV
            base_url = cat_url
            if site_name == 'JableTV' and '?' not in base_url:
                base_url = f'{cat_url}?sort_by=post_date'

            max_pages = MAX_SCAN_PAGES if first_run else DAILY_SCAN_PAGES
            reached_baseline = False
            consecutive_skips = 0

            for page in range(1, max_pages + 1):
                if self._stop.is_set():
                    return
                if reached_baseline:
                    break

                page_url = self._build_page_url(site_name, base_url, page)
                self._log(f'  Page {page}: {page_url}')
                videos = self._fetch_page_for_site(site_name, page_url)
                if not videos:
                    self._log(f'  Page {page}: no videos — end.')
                    break

                self._log(f'  Page {page}: {len(videos)} video(s)')
                page_all_seen = True

                for v in videos:
                    if self._stop.is_set():
                        return
                    vurl = v.get('url', '')
                    if not vurl:
                        continue
                    with self._seen_lock:
                        if vurl in self._seen:
                            continue
                    page_all_seen = False

                    # Date check for JableTV (has detail pages with relative dates)
                    if site_name == 'JableTV':
                        video_dt, rel_text = self._fetch_video_date(vurl)
                        time.sleep(PER_VIDEO_FETCH_DELAY_SEC)
                        if video_dt is None:
                            self._log(f'    [SKIP] no date ({rel_text!r}): {vurl}')
                            consecutive_skips += 1
                            if consecutive_skips >= 10:
                                self._log(f'  10 consecutive skips — moving to next category.')
                                reached_baseline = True
                                break
                            continue
                        if video_dt < baseline_dt:
                            slug = vurl.rstrip('/').split('/')[-1]
                            self._log(f'    [STOP] {slug} — {rel_text} (before {baseline_str})')
                            self._mark_seen(vurl, v.get('title', ''), skipped=True)
                            reached_baseline = True
                            break
                        consecutive_skips = 0
                        self._log(f'    [KEEP] {vurl.rstrip("/").split("/")[-1]} — {rel_text}')
                    else:
                        # MissAV: fetch detail page for release date
                        video_dt, rel_text = self._fetch_missav_video_date(vurl)
                        time.sleep(PER_VIDEO_FETCH_DELAY_SEC)
                        if video_dt is not None and video_dt < baseline_dt:
                            slug = vurl.rstrip('/').split('/')[-1]
                            self._log(f'    [SKIP] {slug} — {rel_text} (before {baseline_str})')
                            self._mark_seen(vurl, v.get('title', ''), skipped=True)
                            consecutive_skips += 1
                            if consecutive_skips >= 10:
                                self._log(f'  10 consecutive skips — moving to next category.')
                                reached_baseline = True
                                break
                            continue
                        consecutive_skips = 0
                        if video_dt:
                            self._log(f'    [KEEP] {vurl.rstrip("/").split("/")[-1]} — {rel_text}')
                        else:
                            self._log(f'    [KEEP] {v.get("title", vurl)[:60]}')

                    v['_site'] = site_name
                    all_new_videos.append(v)

                if not first_run and page_all_seen and not reached_baseline:
                    self._log('  All seen on this page — stopping.')
                    break

        if not all_new_videos:
            self._log(f'No new videos found.')
            cfg['first_run_done'] = True
            save_config(cfg)
            return

        self._log(f'Found {len(all_new_videos)} new video(s). Downloading...')
        for v in all_new_videos:
            if self._stop.is_set():
                return
            self._download_one(v, dest)

        cfg['first_run_done'] = True
        cfg['last_check_iso'] = datetime.now(timezone.utc).isoformat()
        save_config(cfg)

    def _download_one(self, video: dict, dest: str):
        vurl = video['url']
        title = video.get('title', '') or vurl.rstrip('/').split('/')[-1]
        site = video.get('_site', '?')
        self._log(f'↓ [{site}] {title}')

        # Show "preparing" state on progress bar
        with self._progress_lock:
            self._progress = (0, 0, 0, title)

        site_obj = None
        try:
            site_obj = M3U8Sites.CreateSite(vurl, dest)
            if not site_obj or not site_obj.is_url_vaildate():
                self._log(f'  [SKIP] invalid URL: {vurl}')
                self._mark_seen(vurl, title, skipped=True)
                return

            # Wire up progress callback for the progress bar
            def _on_progress(done, total, speed):
                with self._progress_lock:
                    self._progress = (done, total, speed, title)

            site_obj._progress_callback = _on_progress
            site_obj.start_download()

            if getattr(site_obj, '_cancel_job', False):
                self._log('  [CANCELLED]')
                self._cleanup_temp(site_obj)
                return
            self._log(f'  [OK] {title}')
            self._mark_seen(vurl, title)
        except Exception as e:
            self._log(f'  [ERR] {e}')
            if site_obj:
                self._cleanup_temp(site_obj)
        finally:
            with self._progress_lock:
                self._progress = None

    def _cleanup_temp(self, site_obj):
        """Remove temp folder with partial segment clips if final video doesn't exist."""
        try:
            if site_obj.is_target_video_exist():
                return  # Video completed, nothing to clean
            temp = getattr(site_obj, '_temp_folder', None)
            if temp and os.path.isdir(temp):
                shutil.rmtree(temp, ignore_errors=True)
                self._log(f'  [CLEANUP] removed partial clips')
        except Exception:
            pass

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
        self.title(f'{APP_NAME} v2.1.5 — 多站自動下載工具 — by ALOS')
        self.geometry('860x680')
        self.minsize(700, 550)
        self.configure(bg=BG_DARK)

        self._cfg = load_config()
        self._log_queue: list[str] = []
        self._log_lock = threading.Lock()
        self._worker = SmallToolWorker(log_fn=self._enqueue_log)
        self._check_vars: dict[str, tk.BooleanVar] = {}  # "site|cat" -> BooleanVar

        self._build_ui()
        self._load_selections_from_config()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        # Auto-start if configured
        if self._cfg.get('output_folder') and self._cfg.get('selected_targets'):
            self._start_worker()

        self.after(300, self._flush_log_queue)
        self.after(500, self._refresh_progress)

    def _build_ui(self):
        # ── TTK styles (larger checkboxes + progress bar) ───────────
        self._style = ttk.Style()
        self._style.theme_use('clam')
        self._style.configure('Cat.TCheckbutton',
                              background=BG_CARD, foreground=TEXT_PRI,
                              font=('Microsoft JhengHei', 10),
                              indicatorsize=18)
        self._style.map('Cat.TCheckbutton',
                        background=[('active', BG_CARD)],
                        indicatorcolor=[('selected', ACCENT),
                                        ('!selected', BG_INPUT)])
        self._style.configure('All.TCheckbutton',
                              background=BG_CARD, foreground=WARNING,
                              font=('Microsoft JhengHei', 10, 'bold'),
                              indicatorsize=18)
        self._style.map('All.TCheckbutton',
                        background=[('active', BG_CARD)],
                        indicatorcolor=[('selected', ACCENT),
                                        ('!selected', BG_INPUT)])
        self._style.configure('DL.Horizontal.TProgressbar',
                              troughcolor=BG_INPUT,
                              background=ACCENT,
                              thickness=16)

        # ── Header ──────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG_HEADER, height=48)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text='Jable 小工具',
                 bg=BG_HEADER, fg=ACCENT,
                 font=('Microsoft JhengHei', 14, 'bold')).pack(side='left', padx=14)
        tk.Label(hdr, text='多站自動下載',
                 bg=BG_HEADER, fg=TEXT_SEC,
                 font=('Microsoft JhengHei', 11)).pack(side='left', padx=(0, 8))
        tk.Label(hdr, text='v2.1.5  |  by ALOS',
                 bg=BG_HEADER, fg=TEXT_DIM,
                 font=('Microsoft JhengHei', 10)).pack(side='right', padx=14)

        # ── Config row: folder + date ───────────────────────────────
        cfg_frame = tk.Frame(self, bg=BG_DARK)
        cfg_frame.pack(fill='x', padx=14, pady=(10, 4))

        tk.Label(cfg_frame, text='儲存位置:', bg=BG_DARK, fg=TEXT_SEC,
                 font=('Microsoft JhengHei', 10)).pack(side='left')
        self._folder_var = tk.StringVar(value=self._cfg.get('output_folder', ''))
        entry = tk.Entry(cfg_frame, textvariable=self._folder_var,
                         bg=BG_INPUT, fg=TEXT_PRI,
                         insertbackground=TEXT_PRI,
                         relief='flat', bd=4,
                         font=('Microsoft JhengHei', 10))
        entry.pack(side='left', fill='x', expand=True, padx=8)
        tk.Button(cfg_frame, text='瀏覽',
                  bg=BG_CARD, fg=TEXT_PRI,
                  activebackground='#2a2a4a',
                  relief='flat', bd=0, padx=10, pady=4,
                  command=self._pick_folder).pack(side='left')

        # Date row
        date_frame = tk.Frame(self, bg=BG_DARK)
        date_frame.pack(fill='x', padx=14, pady=(0, 6))
        tk.Label(date_frame, text='基準日期:', bg=BG_DARK, fg=TEXT_SEC,
                 font=('Microsoft JhengHei', 10)).pack(side='left')
        self._date_var = tk.StringVar(value=self._cfg.get('baseline_date', DEFAULT_BASELINE_DATE))
        date_entry = tk.Entry(date_frame, textvariable=self._date_var,
                              bg=BG_INPUT, fg=TEXT_PRI,
                              insertbackground=TEXT_PRI,
                              relief='flat', bd=4, width=14,
                              font=('Microsoft JhengHei', 10))
        date_entry.pack(side='left', padx=8)
        tk.Label(date_frame, text='(YYYY-MM-DD，只下載此日期之後的影片)',
                 bg=BG_DARK, fg=TEXT_DIM,
                 font=('Microsoft JhengHei', 9)).pack(side='left')

        # ── Site / Category selection ───────────────────────────────
        sel_label = tk.Label(self, text='選擇網站與分類（可多選）:',
                             bg=BG_DARK, fg=TEXT_SEC,
                             font=('Microsoft JhengHei', 10, 'bold'), anchor='w')
        sel_label.pack(fill='x', padx=14, pady=(4, 2))

        sel_container = tk.Frame(self, bg=BG_DARK)
        sel_container.pack(fill='x', padx=14, pady=(0, 6))

        for site_name, site_info in SITES.items():
            site_frame = tk.LabelFrame(
                sel_container, text=f'  {site_name}  ',
                bg=BG_CARD, fg=ACCENT,
                font=('Microsoft JhengHei', 10, 'bold'),
                bd=1, relief='groove',
                highlightbackground=BORDER, highlightthickness=1,
                padx=8, pady=6)
            site_frame.pack(side='left', fill='both', expand=True, padx=(0, 8))

            # "Select all" for this site
            all_var = tk.BooleanVar(value=False)
            all_key = f'{site_name}|__all__'
            self._check_vars[all_key] = all_var

            all_cb = ttk.Checkbutton(
                site_frame, text='全選',
                style='All.TCheckbutton',
                variable=all_var,
                command=lambda sn=site_name: self._toggle_select_all(sn))
            all_cb.pack(anchor='w', pady=(2, 0))

            # Separator
            tk.Frame(site_frame, bg=BORDER, height=1).pack(fill='x', pady=3)

            # Category checkboxes in columns
            cats = site_info['categories']
            cat_grid = tk.Frame(site_frame, bg=BG_CARD)
            cat_grid.pack(fill='x')

            cols = 3 if len(cats) > 6 else 2
            for i, (cat_name, _) in enumerate(cats):
                key = f'{site_name}|{cat_name}'
                var = tk.BooleanVar(value=False)
                self._check_vars[key] = var
                cb = ttk.Checkbutton(
                    cat_grid, text=cat_name,
                    style='Cat.TCheckbutton',
                    variable=var)
                row, col = divmod(i, cols)
                cb.grid(row=row, column=col, sticky='w', padx=6, pady=2)

        # ── Control row ─────────────────────────────────────────────
        ctrl = tk.Frame(self, bg=BG_DARK)
        ctrl.pack(fill='x', padx=14, pady=(0, 6))

        self._start_btn = tk.Button(
            ctrl, text='▶ 啟動背景偵測',
            bg=ACCENT, fg='#ffffff',
            activebackground=ACCENT_HOVER,
            relief='flat', bd=0, padx=14, pady=6,
            font=('Microsoft JhengHei', 10, 'bold'),
            command=self._start_worker)
        self._start_btn.pack(side='left')

        self._stop_btn = tk.Button(
            ctrl, text='■ 停止',
            bg='#3a1a20', fg=ERROR_C,
            activebackground='#2a1215',
            relief='flat', bd=0, padx=14, pady=6,
            font=('Microsoft JhengHei', 10),
            command=self._stop_worker,
            state='disabled')
        self._stop_btn.pack(side='left', padx=(8, 0))

        self._check_now_btn = tk.Button(
            ctrl, text='↻ 立即檢查一次',
            bg=BG_CARD, fg=TEXT_PRI,
            activebackground='#2a2a4a',
            relief='flat', bd=0, padx=14, pady=6,
            font=('Microsoft JhengHei', 10),
            command=self._check_now)
        self._check_now_btn.pack(side='left', padx=(8, 0))

        self._status_lbl = tk.Label(
            ctrl, text='閒置', bg=BG_DARK, fg=TEXT_DIM,
            font=('Microsoft JhengHei', 10))
        self._status_lbl.pack(side='right')

        # ── Download progress bar ───────────────────────────────────
        prog_outer = tk.Frame(self, bg=BG_CARD, padx=10, pady=6)
        prog_outer.pack(fill='x', padx=14, pady=(0, 4))

        self._prog_title = tk.Label(prog_outer, text='',
                                     bg=BG_CARD, fg=TEXT_PRI,
                                     font=('Microsoft JhengHei', 9),
                                     anchor='w')
        self._prog_title.pack(fill='x')

        bar_row = tk.Frame(prog_outer, bg=BG_CARD)
        bar_row.pack(fill='x', pady=(3, 0))

        self._prog_bar = ttk.Progressbar(
            bar_row, style='DL.Horizontal.TProgressbar',
            maximum=100, value=0, mode='determinate')
        self._prog_bar.pack(side='left', fill='x', expand=True)

        self._prog_pct = tk.Label(bar_row, text='',
                                   bg=BG_CARD, fg=ACCENT,
                                   font=('Consolas', 11, 'bold'),
                                   width=5, anchor='e')
        self._prog_pct.pack(side='left', padx=(8, 0))

        self._prog_info = tk.Label(bar_row, text='',
                                    bg=BG_CARD, fg=TEXT_SEC,
                                    font=('Consolas', 9),
                                    anchor='e')
        self._prog_info.pack(side='right')

        # ── Log box ─────────────────────────────────────────────────
        self._log_box = scrolledtext.ScrolledText(
            self, bg=BG_CARD, fg=TEXT_PRI,
            insertbackground=TEXT_PRI,
            relief='flat', bd=0,
            font=('Consolas', 10),
            wrap='word', state='disabled')
        self._log_box.pack(fill='both', expand=True, padx=14, pady=(0, 10))

        # Footer
        tk.Label(
            self,
            text='提示：關閉視窗會結束程式。最小化後程式仍在背景運行。每 24 小時自動檢查一次。',
            bg=BG_DARK, fg=TEXT_DIM, font=('Microsoft JhengHei', 9)).pack(pady=(0, 8))

    # ── Selection helpers ────────────────────────────────────────────
    def _toggle_select_all(self, site_name: str):
        all_key = f'{site_name}|__all__'
        val = self._check_vars[all_key].get()
        for cat_name, _ in SITES[site_name]['categories']:
            key = f'{site_name}|{cat_name}'
            self._check_vars[key].set(val)

    def _get_selected_targets(self) -> list[dict]:
        targets = []
        for site_name, site_info in SITES.items():
            for cat_name, _ in site_info['categories']:
                key = f'{site_name}|{cat_name}'
                if self._check_vars.get(key, tk.BooleanVar()).get():
                    targets.append({'site': site_name, 'category': cat_name})
        return targets

    def _save_selections_to_config(self):
        self._cfg['selected_targets'] = self._get_selected_targets()
        self._cfg['baseline_date'] = self._date_var.get().strip()
        save_config(self._cfg)

    def _load_selections_from_config(self):
        targets = self._cfg.get('selected_targets', [])
        for t in targets:
            key = f'{t["site"]}|{t["category"]}'
            if key in self._check_vars:
                self._check_vars[key].set(True)

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
        targets = self._get_selected_targets()
        if not targets:
            messagebox.showwarning('未選擇分類', '請至少勾選一個網站分類。')
            return

        # Validate date
        date_str = self._date_var.get().strip()
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            messagebox.showwarning('日期格式錯誤', '基準日期格式應為 YYYY-MM-DD。')
            return

        self._cfg['output_folder'] = folder
        self._cfg['baseline_date'] = date_str
        self._save_selections_to_config()

        sites_summary = ', '.join(set(t['site'] for t in targets))
        cats_summary = ', '.join(t['category'] for t in targets)
        self._log(f'目標: {sites_summary} — {cats_summary}')
        self._log(f'基準日期: {date_str}')

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
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning('缺少資料夾', '請先選擇影片儲存資料夾。')
            return
        targets = self._get_selected_targets()
        if not targets:
            messagebox.showwarning('未選擇分類', '請至少勾選一個網站分類。')
            return
        self._save_selections_to_config()

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

    def _refresh_progress(self):
        prog = self._worker.get_progress()
        if prog:
            done, total, speed, title = prog
            if total > 0:
                pct = int(done * 100 / total)
                self._prog_bar['value'] = pct
                self._prog_pct.configure(text=f'{pct}%')
                speed_str = (f'{speed / 1024:.0f} KB/s' if speed < 1024 * 1024
                             else f'{speed / 1024 / 1024:.1f} MB/s')
                self._prog_info.configure(text=f'{done}/{total} | {speed_str}')
            else:
                # Preparing phase (0, 0, ...)
                self._prog_bar['value'] = 0
                self._prog_pct.configure(text='')
                self._prog_info.configure(text='Preparing...')
            short = title[:50] + '...' if len(title) > 50 else title
            self._prog_title.configure(text=f'↓ {short}')
        else:
            self._prog_bar['value'] = 0
            self._prog_pct.configure(text='')
            self._prog_info.configure(text='')
            self._prog_title.configure(text='')
        self.after(500, self._refresh_progress)

    def _on_close(self):
        self._save_selections_to_config()
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
