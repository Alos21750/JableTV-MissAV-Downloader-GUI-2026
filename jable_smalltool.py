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
from M3U8Sites.M3U8Crawler import fetch_with_mirrors, MirrorsBlockedError
import config
from locales import T, set_lang, get_lang, ui_font, LANGUAGES

# Optional direct-fetch fallback for diagnostics / when cloudscraper struggles
try:
    import cloudscraper
    from bs4 import BeautifulSoup
except Exception:
    cloudscraper = None
    BeautifulSoup = None

# ── Constants ────────────────────────────────────────────────────────
APP_NAME = 'Jable_smalltool'
APP_VERSION = '2.5.2'
_yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
DEFAULT_BASELINE_DATE = _yesterday.strftime('%Y-%m-%d')
DEFAULT_BASELINE_DT = datetime(_yesterday.year, _yesterday.month, _yesterday.day, tzinfo=timezone.utc)
PER_VIDEO_FETCH_DELAY_SEC = 0.3
CHECK_INTERVAL_SEC = 24 * 60 * 60  # 24 hours
SCAN_RETRY_BACKOFF_SEC = 10 * 60
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
    ('今日熱門', 'https://missav.ai/dm296/today-hot'),
    ('本週熱門', 'https://missav.ai/dm170/weekly-hot'),
    ('本月熱門', 'https://missav.ai/dm266/monthly-hot'),
    ('中文字幕', 'https://missav.ai/dm278/chinese-subtitle'),
    ('最近更新', 'https://missav.ai/dm539/new'),
    ('新作上市', 'https://missav.ai/dm632/release'),
    ('無碼流出', 'https://missav.ai/dm816/uncensored-leak'),
    ('FC2', 'https://missav.ai/dm473/fc2'),
    ('麻豆傳媒', 'https://missav.ai/dm63/madou'),
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


def _atomic_write(path: str, text: str) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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
    _atomic_write(CONFIG_PATH, json.dumps(cfg, indent=2, ensure_ascii=False))


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
    _atomic_write(SEEN_PATH, json.dumps(seen, indent=2, ensure_ascii=False))


# ── Downloader core ──────────────────────────────────────────────────
class SmallToolWorker:
    """Background worker that scans selected site/category combos and downloads new videos."""

    def __init__(self, log_fn, status_fn=None):
        self._log = log_fn
        self._status = status_fn
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seen = load_seen()
        self._seen_lock = threading.Lock()
        self._progress = None  # (done, total, speed_bps, title) or None
        self._progress_lock = threading.Lock()
        self._scan_lock = threading.Lock()

    def _set_status(self, key: str, color: str = TEXT_DIM):
        if self._status:
            self._status(key, color)

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
        self._log(T('st_worker_started'))
        while not self._stop.is_set():
            scan_ok = False
            try:
                scan_ok = self._scan_and_download(cfg)
            except Exception as e:
                self._log(f'[ERROR] scan failed: {e}')
            if self._stop.is_set():
                break
            if scan_ok:
                self._set_status('st_running', SUCCESS)
            else:
                self._set_status('st_detect_failed', WARNING)
            cfg = load_config()
            waited = 0
            interval = CHECK_INTERVAL_SEC if scan_ok else SCAN_RETRY_BACKOFF_SEC
            while waited < interval and not self._stop.is_set():
                time.sleep(5)
                waited += 5
        self._log(T('st_worker_stopped'))

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
            def _validate(resp):
                s = BeautifulSoup(resp.content, 'html.parser')
                return bool(s.find(class_='info-header'))
            r, host, reason = fetch_with_mirrors(scraper, vurl, 'jable', _validate, timeout=30)
            if reason == 'blocked':
                return (None, 'BLOCKED')
            if reason != 'ok':
                return (None, '')
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
        if BeautifulSoup is None:
            return (None, '')
        try:
            scraper = MissAVBrowser._get_scraper()
            def _validate(resp):
                s = BeautifulSoup(resp.content, 'html.parser')
                page_text = s.get_text(' ', strip=True)
                return bool(re.search(r'(発売日|發售日|配信開始日|Release\s*Date|上架日期|更新)', page_text, re.I) or
                            s.find('meta', property='og:title') or 'og:title' in resp.text)
            r, host, reason = fetch_with_mirrors(scraper, vurl, 'missav', _validate, timeout=30)
            if reason == 'blocked':
                return (None, 'BLOCKED')
            if reason != 'ok':
                return (None, '')

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
        except MirrorsBlockedError:
            raise
        except Exception as e:
            self._log(f'  [ERR] fetch failed: {e}')
            return []

    def _category_fetch_url(self, site_name: str, cat_name: str, cat_url: str) -> str:
        if site_name == 'MissAV':
            lang = T('missav_lang')
            if lang:
                # Insert the language segment after /dm{N}/ (same scheme as MissAVBrowser),
                # independent of localized display names.
                new_url = re.sub(r'(/dm\d+/)', rf'\1{lang}/', cat_url)
                return new_url
            return cat_url
        # JableTV does not expose language-specific listing variants.
        return cat_url

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
        if not self._scan_lock.acquire(blocking=False):
            self._log(f'[WAIT] {T("st_scan_running")}')
            return False
        try:
            return self._scan_and_download_locked(cfg)
        finally:
            self._scan_lock.release()

    def _scan_and_download_locked(self, cfg: dict):
        dest = cfg.get('output_folder') or ''
        if not dest:
            self._log(f'[WAIT] {T("st_no_output_configured")}')
            return True
        os.makedirs(dest, exist_ok=True)

        targets = cfg.get('selected_targets', [])
        if not targets:
            self._log(f'[WAIT] {T("st_no_targets_selected")}')
            return True

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
        scan_blocked = False
        scan_had_success = False

        for target in targets:
            if self._stop.is_set():
                return False
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

            base_url = self._category_fetch_url(site_name, cat_name, cat_url)
            if site_name == 'JableTV' and '?' not in base_url:
                base_url = f'{cat_url}?sort_by=post_date'

            max_pages = MAX_SCAN_PAGES if first_run else DAILY_SCAN_PAGES
            reached_baseline = False
            consecutive_skips = 0

            for page in range(1, max_pages + 1):
                if self._stop.is_set():
                    return False
                if reached_baseline:
                    break

                page_url = self._build_page_url(site_name, base_url, page)
                self._log(f'  Page {page}: {page_url}')
                try:
                    videos = self._fetch_page_for_site(site_name, page_url)
                except MirrorsBlockedError:
                    scan_blocked = True
                    self._log(f'  [BLOCKED] Cloudflare blocked all mirrors: {page_url}')
                    break
                scan_had_success = True
                if not videos:
                    self._log(f'  Page {page}: no videos — end.')
                    break

                self._log(f'  Page {page}: {len(videos)} video(s)')
                page_all_seen = True

                for v in videos:
                    if self._stop.is_set():
                        return False
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
                        if rel_text == 'BLOCKED':
                            self._log(f'    [BLOCKED] defer date check: {vurl}')
                            continue
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
                        if rel_text == 'BLOCKED':
                            self._log(f'    [BLOCKED] defer date check: {vurl}')
                            continue
                        if video_dt is None:
                            self._log(f'    [SKIP] no confirmed date ({rel_text!r}): {vurl}')
                            consecutive_skips += 1
                            if consecutive_skips >= 10:
                                self._log(f'  10 consecutive skips — moving to next category.')
                                reached_baseline = True
                                break
                            continue
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
                        self._log(f'    [KEEP] {vurl.rstrip("/").split("/")[-1]} — {rel_text}')

                    v['_site'] = site_name
                    all_new_videos.append(v)

                if not first_run and page_all_seen and not reached_baseline:
                    self._log('  All seen on this page — stopping.')
                    break

        if not all_new_videos:
            self._log(f'No new videos found.')
            if scan_blocked or not scan_had_success:
                self._log('[WARN] Scan incomplete — will retry before marking first run done.')
                return False
            cfg['first_run_done'] = True
            save_config(cfg)
            return True

        self._log(f'Found {len(all_new_videos)} new video(s). Downloading...')
        for v in all_new_videos:
            if self._stop.is_set():
                return False
            self._download_one(v, dest)

        if scan_blocked or not scan_had_success:
            self._log('[WARN] Scan incomplete — first run flag not updated.')
            return False
        cfg['first_run_done'] = True
        cfg['last_check_iso'] = datetime.now(timezone.utc).isoformat()
        save_config(cfg)
        return True

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
        self._lang_code_by_name = {name: code for code, name in LANGUAGES}
        self._lang_name_by_code = {code: name for code, name in LANGUAGES}

        stored = config.get_ui_lang()
        set_lang(stored or 'en')
        self._needs_lang_prompt = (stored is None)

        self._update_window_title()
        self.geometry('860x680')
        self.minsize(700, 550)
        self.configure(bg=BG_DARK)

        self._cfg = load_config()
        self._log_queue: list[str] = []
        self._log_lock = threading.Lock()
        self._is_closing = False
        self._rebuilding = False
        self._build_gen = 0
        self._status_key = 'st_idle'
        self._status_fg = TEXT_DIM
        self._worker = SmallToolWorker(log_fn=self._enqueue_log,
                                       status_fn=self._set_status_threadsafe)
        self._check_vars: dict[str, tk.BooleanVar] = {}  # "site|cat" -> BooleanVar

        self._build_ui()
        self._load_selections_from_config()
        self._sync_select_all_vars()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        # Auto-start if configured
        if self._cfg.get('output_folder') and self._cfg.get('selected_targets'):
            self._start_worker()

        self._schedule_log_flush()
        self._schedule_progress_refresh()
        if self._needs_lang_prompt:
            self.after(300, self._first_run_language_prompt)

    def _update_window_title(self):
        self.title(T('st_window_title', app=APP_NAME, version=APP_VERSION))

    def _ask_language_first_run(self):
        result = {'code': 'en'}
        popup = tk.Toplevel(self)
        popup.title(T('st_lang_picker_title'))
        popup.configure(bg=BG_DARK)
        popup.resizable(False, False)
        popup.transient(self)

        picker_font = ui_font()
        tk.Label(
            popup, text=T('st_lang_picker_title'),
            bg=BG_DARK, fg=TEXT_PRI,
            font=(picker_font, 14, 'bold')).pack(padx=28, pady=(24, 12))

        def _choose(code='en'):
            result['code'] = code
            try:
                popup.grab_release()
            except tk.TclError:
                pass
            popup.destroy()

        for code, name in LANGUAGES:
            tk.Button(
                popup, text=name, width=24,
                bg=BG_CARD, fg=TEXT_PRI,
                activebackground=ACCENT, activeforeground='#ffffff',
                relief='flat', bd=0, padx=12, pady=8,
                font=(picker_font, 11),
                command=lambda c=code: _choose(c)).pack(padx=28, pady=4)

        popup.protocol('WM_DELETE_WINDOW', lambda: _choose('en'))
        popup.update_idletasks()
        x = max(0, (popup.winfo_screenwidth() - popup.winfo_width()) // 2)
        y = max(0, (popup.winfo_screenheight() - popup.winfo_height()) // 3)
        popup.geometry(f'+{x}+{y}')
        popup.grab_set()
        self.wait_window(popup)
        return result['code']

    def _first_run_language_prompt(self):
        if getattr(self, '_is_closing', False):
            return
        code = self._ask_language_first_run()
        config.set_ui_lang(code)
        if code != get_lang():
            self._apply_language(code)

    def _on_lang_change(self, name: str):
        code = self._lang_code_by_name.get(name, 'en')
        if code != get_lang():
            self._apply_language(code)

    def _snapshot_ui_state(self) -> dict:
        check_state = 'normal'
        if hasattr(self, '_check_now_btn'):
            try:
                check_state = self._check_now_btn.cget('state')
            except tk.TclError:
                pass
        return {
            'folder': self._folder_var.get() if hasattr(self, '_folder_var') else self._cfg.get('output_folder', ''),
            'baseline_date': self._date_var.get() if hasattr(self, '_date_var') else self._cfg.get('baseline_date', DEFAULT_BASELINE_DATE),
            'selected_targets': self._get_selected_targets() if self._check_vars else self._cfg.get('selected_targets', []),
            'prefer_lowest_res': self._cfg.get('prefer_lowest_res', False),
            'running': self._worker.is_running(),
            'check_now_state': check_state,
            'status_key': self._status_key,
            'status_fg': self._status_fg,
        }

    def _restore_ui_state(self, snapshot: dict):
        self._cfg['output_folder'] = snapshot['folder']
        self._cfg['baseline_date'] = snapshot['baseline_date']
        self._cfg['prefer_lowest_res'] = snapshot['prefer_lowest_res']
        self._folder_var.set(snapshot['folder'])
        self._date_var.set(snapshot['baseline_date'])
        self._res_var.set(self._resolution_label())

        for var in self._check_vars.values():
            var.set(False)
        for target in snapshot['selected_targets']:
            key = f'{target["site"]}|{target["category"]}'
            if key in self._check_vars:
                self._check_vars[key].set(True)
        self._sync_select_all_vars()

        running = snapshot['running']
        self._start_btn.configure(state='disabled' if running else 'normal')
        self._stop_btn.configure(state='normal' if running else 'disabled')
        if running and snapshot['status_key'] in ('st_idle', 'st_stopped'):
            self._set_status_key('st_running', SUCCESS)
        else:
            self._set_status_key(snapshot['status_key'], snapshot['status_fg'])
        self._check_now_btn.configure(state=snapshot['check_now_state'])

    def _apply_language(self, code: str):
        self._rebuilding = True
        try:
            snapshot = self._snapshot_ui_state()
            set_lang(code)
            config.set_ui_lang(code)
            self._build_gen += 1

            for child in self.winfo_children():
                try:
                    child.destroy()
                except tk.TclError:
                    pass

            self._check_vars = {}
            self._build_ui()
            self._restore_ui_state(snapshot)
            self._update_window_title()
        finally:
            self._rebuilding = False

    def _resolution_label(self) -> str:
        return T('st_resolution_lowest') if self._cfg.get('prefer_lowest_res', False) else T('st_resolution_highest')

    def _set_status_key(self, key: str, fg: str = TEXT_DIM):
        self._status_key = key
        self._status_fg = fg
        text = T(key) if key.startswith('st_') else key
        if hasattr(self, '_status_lbl'):
            try:
                self._status_lbl.configure(text=text, fg=fg)
            except tk.TclError:
                pass

    def _build_ui(self):
        font_family = ui_font()
        self._update_window_title()

        # ── TTK styles (larger checkboxes + progress bar) ───────────
        self._style = ttk.Style()
        self._style.theme_use('clam')
        self._style.configure('Cat.TCheckbutton',
                              background=BG_CARD, foreground=TEXT_PRI,
                              font=(font_family, 10),
                              indicatorsize=18)
        self._style.map('Cat.TCheckbutton',
                        background=[('active', BG_CARD)],
                        indicatorcolor=[('selected', ACCENT),
                                        ('!selected', BG_INPUT)])
        self._style.configure('All.TCheckbutton',
                              background=BG_CARD, foreground=WARNING,
                              font=(font_family, 10, 'bold'),
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
        tk.Label(hdr, text=T('st_header'),
                 bg=BG_HEADER, fg=ACCENT,
                 font=(font_family, 14, 'bold')).pack(side='left', padx=14)
        tk.Label(hdr, text=T('st_subtitle'),
                 bg=BG_HEADER, fg=TEXT_SEC,
                 font=(font_family, 11)).pack(side='left', padx=(0, 8))

        right_info = tk.Frame(hdr, bg=BG_HEADER)
        right_info.pack(side='right', padx=14)
        tk.Label(right_info, text=T('st_version_by', version=APP_VERSION),
                 bg=BG_HEADER, fg=TEXT_DIM,
                 font=('Consolas', 10)).pack(side='right', padx=(10, 0))
        self._lang_var = tk.StringVar(value=self._lang_name_by_code.get(get_lang(), 'English'))
        lang_menu = tk.OptionMenu(
            right_info, self._lang_var, *[name for _, name in LANGUAGES],
            command=self._on_lang_change)
        lang_menu.configure(bg=BG_INPUT, fg=TEXT_PRI, activebackground=BG_CARD,
                            activeforeground=TEXT_PRI, relief='flat', bd=2,
                            font=(font_family, 9), highlightthickness=0)
        lang_menu['menu'].configure(bg=BG_INPUT, fg=TEXT_PRI,
                                    activebackground=ACCENT, activeforeground='#ffffff',
                                    font=(font_family, 9))
        lang_menu.pack(side='right')
        tk.Label(right_info, text=T('st_lang_label'),
                 bg=BG_HEADER, fg=TEXT_DIM,
                 font=(font_family, 9)).pack(side='right', padx=(0, 6))

        # ── Config row: folder + date ───────────────────────────────
        cfg_frame = tk.Frame(self, bg=BG_DARK)
        cfg_frame.pack(fill='x', padx=14, pady=(10, 4))

        tk.Label(cfg_frame, text=T('st_save_location'), bg=BG_DARK, fg=TEXT_SEC,
                 font=(font_family, 10)).pack(side='left')
        self._folder_var = tk.StringVar(value=self._cfg.get('output_folder', ''))
        entry = tk.Entry(cfg_frame, textvariable=self._folder_var,
                         bg=BG_INPUT, fg=TEXT_PRI,
                         insertbackground=TEXT_PRI,
                         relief='flat', bd=4,
                         font=(font_family, 10))
        entry.pack(side='left', fill='x', expand=True, padx=8)
        tk.Button(cfg_frame, text=T('st_browse'),
                  bg=BG_CARD, fg=TEXT_PRI,
                  activebackground='#2a2a4a',
                  relief='flat', bd=0, padx=10, pady=4,
                  font=(font_family, 10),
                  command=self._pick_folder).pack(side='left')

        # Date row
        date_frame = tk.Frame(self, bg=BG_DARK)
        date_frame.pack(fill='x', padx=14, pady=(0, 6))
        tk.Label(date_frame, text=T('st_baseline_date'), bg=BG_DARK, fg=TEXT_SEC,
                 font=(font_family, 10)).pack(side='left')
        self._date_var = tk.StringVar(value=self._cfg.get('baseline_date', DEFAULT_BASELINE_DATE))
        date_entry = tk.Entry(date_frame, textvariable=self._date_var,
                              bg=BG_INPUT, fg=TEXT_PRI,
                              insertbackground=TEXT_PRI,
                              relief='flat', bd=4, width=14,
                              font=(font_family, 10))
        date_entry.pack(side='left', padx=8)
        tk.Label(date_frame, text=T('st_date_hint'),
                 bg=BG_DARK, fg=TEXT_DIM,
                 font=(font_family, 9)).pack(side='left')

        # Resolution row
        res_frame = tk.Frame(self, bg=BG_DARK)
        res_frame.pack(fill='x', padx=14, pady=(0, 6))
        tk.Label(res_frame, text=T('st_resolution'), bg=BG_DARK, fg=TEXT_SEC,
                 font=(font_family, 10)).pack(side='left')
        self._res_var = tk.StringVar(value=self._resolution_label())
        res_menu = tk.OptionMenu(res_frame, self._res_var, T('st_resolution_highest'), T('st_resolution_lowest'),
                                 command=self._on_res_change)
        res_menu.configure(bg=BG_INPUT, fg=TEXT_PRI, activebackground=BG_CARD,
                           activeforeground=TEXT_PRI, relief='flat', bd=4,
                           font=(font_family, 10), highlightthickness=0)
        res_menu['menu'].configure(bg=BG_INPUT, fg=TEXT_PRI,
                                   activebackground=ACCENT, activeforeground='#ffffff',
                                   font=(font_family, 10))
        res_menu.pack(side='left', padx=8)
        # Apply saved preference immediately (before auto-start)
        from M3U8Sites.M3U8Crawler import set_prefer_lowest_res
        set_prefer_lowest_res(bool(self._cfg.get('prefer_lowest_res', False)))

        # ── Site / Category selection ───────────────────────────────
        sel_label = tk.Label(self, text=T('st_select_hint'),
                             bg=BG_DARK, fg=TEXT_SEC,
                             font=(font_family, 10, 'bold'), anchor='w')
        sel_label.pack(fill='x', padx=14, pady=(4, 2))

        sel_container = tk.Frame(self, bg=BG_DARK)
        sel_container.pack(fill='x', padx=14, pady=(0, 6))

        for site_name, site_info in SITES.items():
            site_frame = tk.LabelFrame(
                sel_container, text=f'  {site_name}  ',
                bg=BG_CARD, fg=ACCENT,
                font=(font_family, 10, 'bold'),
                bd=1, relief='groove',
                highlightbackground=BORDER, highlightthickness=1,
                padx=8, pady=6)
            site_frame.pack(side='left', fill='both', expand=True, padx=(0, 8))

            # "Select all" for this site
            all_var = tk.BooleanVar(value=False)
            all_key = f'{site_name}|__all__'
            self._check_vars[all_key] = all_var

            all_cb = ttk.Checkbutton(
                site_frame, text=T('st_select_all'),
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
            ctrl, text=T('st_start'),
            bg=ACCENT, fg='#ffffff',
            activebackground=ACCENT_HOVER,
            relief='flat', bd=0, padx=14, pady=6,
            font=(font_family, 10, 'bold'),
            command=self._start_worker)
        self._start_btn.pack(side='left')

        self._stop_btn = tk.Button(
            ctrl, text=T('st_stop'),
            bg='#3a1a20', fg=ERROR_C,
            activebackground='#2a1215',
            relief='flat', bd=0, padx=14, pady=6,
            font=(font_family, 10),
            command=self._stop_worker,
            state='disabled')
        self._stop_btn.pack(side='left', padx=(8, 0))

        self._check_now_btn = tk.Button(
            ctrl, text=T('st_check_now'),
            bg=BG_CARD, fg=TEXT_PRI,
            activebackground='#2a2a4a',
            relief='flat', bd=0, padx=14, pady=6,
            font=(font_family, 10),
            command=self._check_now)
        self._check_now_btn.pack(side='left', padx=(8, 0))

        self._status_lbl = tk.Label(
            ctrl, text=T(self._status_key), bg=BG_DARK, fg=self._status_fg,
            font=(font_family, 10))
        self._status_lbl.pack(side='right')

        # ── Download progress bar ───────────────────────────────────
        prog_outer = tk.Frame(self, bg=BG_CARD, padx=10, pady=6)
        prog_outer.pack(fill='x', padx=14, pady=(0, 4))

        self._prog_title = tk.Label(prog_outer, text='',
                                     bg=BG_CARD, fg=TEXT_PRI,
                                     font=(font_family, 9),
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
            text=T('st_footer'),
            bg=BG_DARK, fg=TEXT_DIM, font=(font_family, 9)).pack(pady=(0, 8))

    # ── Selection helpers ────────────────────────────────────────────
    def _toggle_select_all(self, site_name: str):
        all_key = f'{site_name}|__all__'
        val = self._check_vars[all_key].get()
        for cat_name, _ in SITES[site_name]['categories']:
            key = f'{site_name}|{cat_name}'
            self._check_vars[key].set(val)

    def _sync_select_all_vars(self):
        for site_name, site_info in SITES.items():
            all_key = f'{site_name}|__all__'
            if all_key not in self._check_vars:
                continue
            cat_keys = [f'{site_name}|{cat_name}' for cat_name, _ in site_info['categories']]
            self._check_vars[all_key].set(all(self._check_vars[key].get() for key in cat_keys))

    def _get_selected_targets(self) -> list[dict]:
        targets = []
        for site_name, site_info in SITES.items():
            for cat_name, _ in site_info['categories']:
                key = f'{site_name}|{cat_name}'
                if self._check_vars.get(key, tk.BooleanVar()).get():
                    targets.append({'site': site_name, 'category': cat_name})
        return targets

    def _validate_baseline_date(self) -> Optional[str]:
        date_str = self._date_var.get().strip()
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            messagebox.showwarning(T('st_bad_date'), T('st_bad_date_msg'))
            return None
        return date_str

    def _save_selections_to_config(self, date_str: Optional[str] = None) -> bool:
        if date_str is None:
            date_str = self._validate_baseline_date()
            if not date_str:
                return False
        self._cfg['selected_targets'] = self._get_selected_targets()
        self._cfg['baseline_date'] = date_str
        save_config(self._cfg)
        return True

    def _load_selections_from_config(self):
        targets = self._cfg.get('selected_targets', [])
        for t in targets:
            key = f'{t["site"]}|{t["category"]}'
            if key in self._check_vars:
                self._check_vars[key].set(True)

    # ── Handlers ─────────────────────────────────────────────────────
    def _pick_folder(self):
        d = filedialog.askdirectory(title=T('st_choose_folder'))
        if d:
            self._folder_var.set(d)
            self._cfg['output_folder'] = d
            save_config(self._cfg)
            self._log(T('st_folder_set', path=d))

    def _on_res_change(self, val):
        from M3U8Sites.M3U8Crawler import set_prefer_lowest_res
        prefer_low = (val == T('st_resolution_lowest'))
        set_prefer_lowest_res(prefer_low)
        self._cfg['prefer_lowest_res'] = prefer_low
        save_config(self._cfg)

    def _start_worker(self):
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning(T('st_no_folder'), T('st_no_folder_msg'))
            return
        targets = self._get_selected_targets()
        if not targets:
            messagebox.showwarning(T('st_no_cat'), T('st_no_cat_msg'))
            return

        date_str = self._validate_baseline_date()
        if not date_str:
            return

        self._cfg['output_folder'] = folder
        self._cfg['baseline_date'] = date_str
        if not self._save_selections_to_config(date_str):
            return

        sites_summary = ', '.join(set(t['site'] for t in targets))
        cats_summary = ', '.join(t['category'] for t in targets)
        self._log(T('st_target_log', sites=sites_summary, categories=cats_summary))
        self._log(T('st_baseline_log', date=date_str))

        self._worker.start()
        self._start_btn.configure(state='disabled')
        self._stop_btn.configure(state='normal')
        self._set_status_key('st_running', SUCCESS)
        self._log(T('st_started_msg'))

    def _stop_worker(self):
        self._worker.stop()
        self._start_btn.configure(state='normal')
        self._stop_btn.configure(state='disabled')
        self._set_status_key('st_stopped', TEXT_DIM)

    def _check_now(self):
        if self._worker.is_running():
            self._log(T('st_scan_running'))
            return
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning(T('st_no_folder'), T('st_no_folder_msg'))
            return
        targets = self._get_selected_targets()
        if not targets:
            messagebox.showwarning(T('st_no_cat'), T('st_no_cat_msg'))
            return
        date_str = self._validate_baseline_date()
        if not date_str:
            return
        if not self._save_selections_to_config(date_str):
            return
        self._check_now_btn.configure(state='disabled')

        def _once():
            cfg = load_config()
            try:
                ok = self._worker._scan_and_download(cfg)
                if not ok:
                    self._set_status_threadsafe('st_detect_failed', WARNING)
            except Exception as e:
                self._log(f'[ERR] {e}')
                self._set_status_threadsafe('st_detect_failed', WARNING)
            finally:
                try:
                    self.after(0, self._enable_check_now_btn)
                except tk.TclError:
                    pass

        threading.Thread(target=_once, daemon=True).start()
        self._log(T('st_checking_now'))

    # ── Logging (thread-safe) ────────────────────────────────────────
    def _enable_check_now_btn(self):
        if self._is_closing or not hasattr(self, '_check_now_btn'):
            return
        try:
            self._check_now_btn.configure(state='normal')
        except tk.TclError:
            pass

    def _set_status_threadsafe(self, key: str, fg: str = TEXT_DIM):
        def _apply():
            if not self._is_closing:
                self._set_status_key(key, fg)
        try:
            self.after(0, _apply)
        except tk.TclError:
            pass

    def _enqueue_log(self, msg: str):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        with self._log_lock:
            self._log_queue.append(line)

    def _log(self, msg: str):
        self._enqueue_log(msg)

    def _schedule_log_flush(self):
        gen = self._build_gen
        self.after(300, lambda gen=gen: self._flush_log_queue(gen))

    def _flush_log_queue(self, gen: int):
        if self._is_closing:
            return
        if (self._rebuilding or gen != self._build_gen
                or getattr(self, '_log_box', None) is None):
            try:
                self.after(300, lambda gen=self._build_gen: self._flush_log_queue(gen))
            except tk.TclError:
                pass
            return
        with self._log_lock:
            pending = self._log_queue[:]
            self._log_queue.clear()
        if pending:
            try:
                self._log_box.configure(state='normal')
                for line in pending:
                    self._log_box.insert('end', line + '\n')
                self._log_box.see('end')
                self._log_box.configure(state='disabled')
            except (tk.TclError, AttributeError):
                if not self._is_closing:
                    try:
                        self.after(300, lambda gen=self._build_gen: self._flush_log_queue(gen))
                    except tk.TclError:
                        pass
                return
        try:
            self.after(300, lambda gen=self._build_gen: self._flush_log_queue(gen))
        except tk.TclError:
            pass

    def _schedule_progress_refresh(self):
        gen = self._build_gen
        self.after(500, lambda gen=gen: self._refresh_progress(gen))

    def _refresh_progress(self, gen: int):
        if self._is_closing:
            return
        if (self._rebuilding or gen != self._build_gen
                or getattr(self, '_prog_bar', None) is None
                or getattr(self, '_prog_pct', None) is None
                or getattr(self, '_prog_info', None) is None
                or getattr(self, '_prog_title', None) is None):
            try:
                self.after(500, lambda gen=self._build_gen: self._refresh_progress(gen))
            except tk.TclError:
                pass
            return
        prog = self._worker.get_progress()
        try:
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
                    self._prog_info.configure(text=T('st_preparing'))
                short = title[:50] + '...' if len(title) > 50 else title
                self._prog_title.configure(text=f'↓ {short}')
            else:
                self._prog_bar['value'] = 0
                self._prog_pct.configure(text='')
                self._prog_info.configure(text='')
                self._prog_title.configure(text='')
        except (tk.TclError, AttributeError):
            if not self._is_closing:
                try:
                    self.after(500, lambda gen=self._build_gen: self._refresh_progress(gen))
                except tk.TclError:
                    pass
            return
        try:
            self.after(500, lambda gen=self._build_gen: self._refresh_progress(gen))
        except tk.TclError:
            pass

    def _on_close(self):
        self._is_closing = True
        self._build_gen += 1
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
