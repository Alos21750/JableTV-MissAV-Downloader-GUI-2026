#!/usr/bin/env python
# coding: utf-8
"""Jable SmallTool — auto-downloader with site/category/date selection.

Supports JableTV, MissAV, and SupJav. The user picks which sites and categories
(multi-select), and a baseline date. The worker scans selected categories
daily and downloads any new video it hasn't seen before.

Author: ALOS
"""

import calendar
import ctypes
import json
import os
import shutil
import sys
import threading
import time
import tkinter as tk
import re
from datetime import date, datetime, timezone, timedelta
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

# Enable DPI awareness (Windows)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# --- issue #23: harden the SSL cert path before curl_cffi (pulled in by M3U8Sites)
# imports, so a non-UTF-8 OpenSSL/cert default path can't crash startup. ---
import os as _os, ssl as _ssl
try:
    import certifi as _certifi
    _ca = _certifi.where()
    if _ca and _os.path.exists(_ca):
        _os.environ.setdefault('SSL_CERT_FILE', _ca)
        _os.environ.setdefault('SSL_CERT_DIR', _os.path.dirname(_ca))
        try:
            _ssl.get_default_verify_paths()
        except (UnicodeDecodeError, SystemError):
            _dvp = _ssl.DefaultVerifyPaths(_ca, _os.path.dirname(_ca),
                                           'SSL_CERT_FILE', _ca,
                                           'SSL_CERT_DIR', _os.path.dirname(_ca))
            _ssl.get_default_verify_paths = lambda: _dvp
except Exception:
    pass

# issue #24: global crash logger -> crash_log.txt + copyable dialog
try:
    import crashlog
    crashlog.install()
except Exception:
    pass

import M3U8Sites
from M3U8Sites.SiteJableTV import JableTVBrowser
from M3U8Sites.SiteMissAV import MissAVBrowser
from M3U8Sites.SiteSupJav import SupJavBrowser
from M3U8Sites.M3U8Crawler import fetch_with_mirrors, MirrorsBlockedError
import config
from locales import T, set_lang, get_lang, ui_font, LANGUAGES
from smalltool_categories import (
    SITES,
    find_target,
    group_label,
    iter_targets,
    selection_key,
    target_label,
)
from video_identity import (
    DEFAULT_VERSION_PREFERENCE,
    VALID_VERSION_PREFERENCES,
    dedupe_video_candidates,
    normalize_version_preference,
    site_from_url,
    url_slug,
    video_code,
    video_versions,
)
from ui_theme import (
    ACCENT, ACCENT_HOVER, ACCENT_DIM, SUCCESS, WARNING, ERROR_C, ERROR_DIM,
    BG_DARK, BG_CARD, BG_CARD_HOVER, BG_INPUT, BG_HEADER, BG_SECTION,
    BG_BADGE, TEXT_PRI, TEXT_SEC, TEXT_DIM, BORDER, BORDER_HOVER,
    BORDER_CARD, WHITE, CARD_RADIUS, CONTROL_RADIUS, color_for_mode,
    category_columns_for_width,
)

# Optional direct-fetch fallback for diagnostics / when cloudscraper struggles
try:
    import cloudscraper
    from bs4 import BeautifulSoup
except Exception:
    cloudscraper = None
    BeautifulSoup = None

# ── Constants ────────────────────────────────────────────────────────
APP_NAME = 'Jable_smalltool'
APP_VERSION = '2.5.30'
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
# The grouped stable-ID registry lives in smalltool_categories.py.

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _default_output_folder() -> str:
    """Portable fallback used when the user has not selected a folder."""
    return os.path.join(APP_DIR, 'tmp')


def _months_before(base_date: date, months: int) -> date:
    """Return a calendar-month offset, clamping to the target month's last day."""
    if months < 0:
        raise ValueError('months must be non-negative')
    month_index = base_date.year * 12 + base_date.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _missav_video_code(video: dict) -> str:
    candidate = dict(video)
    candidate['_site'] = 'MissAV'
    return video_code(candidate)


def _missav_video_version(video: dict) -> str:
    candidate = dict(video)
    candidate['_site'] = 'MissAV'
    versions = video_versions(candidate)
    if 'chinese-subtitle' in versions:
        return 'chinese-subtitle'
    if 'uncensored' in versions:
        return 'uncensored'
    return 'standard'


def _dedupe_missav_candidates(
        videos: list[dict],
        preference: str = DEFAULT_VERSION_PREFERENCE):
    """Backward-compatible wrapper for older tests and integrations."""
    return dedupe_video_candidates(videos, preference)


def _fallback_state_dir() -> str:
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'JableTV Downloader', 'smalltool')


def _state_dir_is_readable(path: str) -> bool:
    try:
        return os.path.isdir(path) and os.access(path, os.R_OK)
    except Exception:
        return False


def _state_dir_is_writable(path: str) -> bool:
    probe = os.path.join(path, f'.write_test_{os.getpid()}')
    try:
        os.makedirs(path, exist_ok=True)
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('ok')
        os.remove(probe)
        return True
    except Exception:
        try:
            if os.path.exists(probe):
                os.remove(probe)
        except Exception:
            pass
        return False


def _select_state_dir() -> str:
    portable = os.path.join(APP_DIR, f'.{APP_NAME}')
    try:
        if _state_dir_is_readable(portable):
            return portable
        if _state_dir_is_writable(portable):
            return portable
    except Exception:
        pass
    try:
        return _fallback_state_dir()
    except Exception:
        return portable


STATE_DIR = _select_state_dir()
CONFIG_PATH = os.path.join(STATE_DIR, 'config.json')
SEEN_PATH = os.path.join(STATE_DIR, 'seen.json')
_VALID_RESOLUTION_PREFS = {'highest', 'lowest', '1080', '720', '480', '360'}


def _normalize_version_pref(cfg: dict) -> str:
    value = cfg.get(
        'version_preference', cfg.get('missav_version_preference'))
    return normalize_version_preference(value)


def _targets_for_scan(targets: list[dict], version_preference: str) -> list[dict]:
    """Add MissAV's category×subtitle view before the normal fallback view."""
    expanded = []
    for target in targets:
        target_id = str(target.get('id') or '')
        if (target.get('site') == 'MissAV' and
                version_preference == 'chinese-subtitle' and
                target_id.startswith(('genres:', 'makers:', 'provider:'))):
            preferred = dict(target)
            preferred['_missav_filter'] = 'chinese-subtitle'
            expanded.append(preferred)
        expanded.append(target)
    return expanded

# ── Persistence ──────────────────────────────────────────────────────
def _ensure_state_dir() -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
    except Exception:
        pass


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
                cfg = json.load(f)
            if isinstance(cfg, dict):
                if not str(cfg.get('output_folder') or '').strip():
                    cfg['output_folder'] = _default_output_folder()
                cfg['version_preference'] = _normalize_version_pref(cfg)
                cfg.pop('missav_version_preference', None)
                return cfg
        except Exception:
            pass
    return {
        'output_folder': _default_output_folder(),
        'baseline_date': DEFAULT_BASELINE_DATE,
        'version_preference': DEFAULT_VERSION_PREFERENCE,
        'first_run_done': False,
        # list of {"site": "JableTV", "id": "category:chinese-subtitle", ...}
        'selected_targets': [],
    }


def save_config(cfg: dict) -> None:
    _ensure_state_dir()
    _atomic_write(CONFIG_PATH, json.dumps(cfg, indent=2, ensure_ascii=False))


def _normalize_resolution_pref(cfg: dict) -> str:
    pref = cfg.get('resolution')
    if isinstance(pref, str):
        pref = pref.strip().lower()
        if pref in _VALID_RESOLUTION_PREFS:
            return pref
    if 'resolution' not in cfg:
        return 'lowest' if cfg.get('prefer_lowest_res', False) else 'highest'
    return 'highest'


def load_seen() -> dict:
    _ensure_state_dir()
    if os.path.exists(SEEN_PATH):
        try:
            with open(SEEN_PATH, 'r', encoding='utf-8') as f:
                seen = json.load(f)
            return seen if isinstance(seen, dict) else {}
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
        self._scan_state = None  # (site, category, page, eligible_count) or None
        self._scan_state_lock = threading.Lock()
        self._scan_lock = threading.Lock()
        self._active_site = None
        self._active_site_lock = threading.Lock()

    def _set_status(self, key: str, color: str = TEXT_DIM):
        if self._status:
            self._status(key, color)

    def get_progress(self):
        with self._progress_lock:
            return self._progress

    def get_scan_state(self):
        with self._scan_state_lock:
            return self._scan_state

    def _set_scan_state(self, site=None, category='', page=0, eligible_count=0):
        with self._scan_state_lock:
            self._scan_state = (
                (site, category, page, eligible_count) if site else None)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._set_scan_state()

    def cancel_active_download(self):
        with self._active_site_lock:
            site_obj = self._active_site
        if site_obj and hasattr(site_obj, 'cancel_download'):
            try:
                site_obj.cancel_download()
            except Exception:
                pass

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
        text = rel_text.strip()

        def _apply_delta(n: int, unit: str) -> Optional[datetime]:
            if unit in ('秒', 'second'):
                delta = timedelta(seconds=n)
            elif unit in ('分鐘', '分', 'minute'):
                delta = timedelta(minutes=n)
            elif unit in ('小時', '時間', 'hour'):
                delta = timedelta(hours=n)
            elif unit in ('天', '日', 'day'):
                delta = timedelta(days=n)
            elif unit in ('星期', '週', '周', '週間', 'week'):
                delta = timedelta(weeks=n)
            elif unit in ('月', '個月', 'ヶ月', 'か月', 'カ月', 'month'):
                delta = timedelta(days=n * 30)
            elif unit in ('年', '個年', 'year'):
                delta = timedelta(days=n * 365)
            else:
                return None
            return now - delta

        m = re.match(
            r'\s*(\d+|[一二兩三四五六七八九十]+)'
            r'\s*(個)?\s*'
            r'(分鐘|小時|天|星期|週|周|個?月|個?年)\s*前',
            text,
        )
        if m:
            num_raw = m.group(1)
            if num_raw.isdigit():
                n = int(num_raw)
            else:
                n = cls._parse_cn_number(num_raw)
                if n is None:
                    return None
            return _apply_delta(n, m.group(3))

        low = text.lower()
        if low in ('just now', 'today'):
            return now
        if low == 'yesterday':
            return now - timedelta(days=1)
        if low == 'a minute ago':
            return now - timedelta(minutes=1)
        if low == 'an hour ago':
            return now - timedelta(hours=1)
        m = re.match(
            r'\s*(\d+)\s*'
            r'(second|minute|hour|day|week|month|year)s?\s+ago',
            low,
            re.I,
        )
        if m:
            return _apply_delta(int(m.group(1)), m.group(2).lower())

        if text == '今日':
            return now
        if text == '昨日':
            return now - timedelta(days=1)
        m = re.match(r'\s*(\d+)\s*(秒|分|時間|週間|日|ヶ月|か月|カ月|年)\s*前', text)
        if m:
            return _apply_delta(int(m.group(1)), m.group(2))
        return None

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

    @staticmethod
    def _parse_supjav_listing_date(value: str) -> Optional[datetime]:
        try:
            return datetime.strptime((value or '').strip(), '%Y/%m/%d').replace(
                tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

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
        if site_name == 'SupJav':
            return SupJavBrowser._with_lang(cat_url, T('supjav_lang'))
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
        return SITES[site_name]['browser'].page_url(base_url, page)

    def _scan_and_download(self, cfg: dict):
        if not self._scan_lock.acquire(blocking=False):
            self._log(f'[WAIT] {T("st_scan_running")}')
            return False
        try:
            return self._scan_and_download_locked(cfg)
        finally:
            self._set_scan_state()
            self._scan_lock.release()

    def _scan_and_download_locked(self, cfg: dict):
        dest = str(cfg.get('output_folder') or '').strip() or _default_output_folder()
        cfg['output_folder'] = dest
        version_preference = _normalize_version_pref(cfg)
        cfg['version_preference'] = version_preference
        cfg.pop('missav_version_preference', None)
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

        self._set_status('st_scanning', ACCENT)
        self._log(f'{"First run" if first_run else "Daily check"} — '
                  f'{len(targets)} target(s), baseline {baseline_str}')

        all_new_videos = []
        scan_blocked = False
        scan_had_success = False

        for target in _targets_for_scan(targets, version_preference):
            if self._stop.is_set():
                return False
            site_name = target['site']
            if site_name not in SITES:
                self._log(f'[WARN] site not found: {site_name}')
                continue
            cat = find_target(site_name, target.get('id'), target.get('category'))
            if not cat:
                cat_name = target.get('category') or target.get('id') or '?'
                self._log(f'[WARN] category not found: {site_name}/{cat_name}')
                continue
            cat_name = target_label(cat)
            cat_url = cat['url']

            self._log(f'── {site_name} / {cat_name} ──')

            base_url = self._category_fetch_url(site_name, cat_name, cat_url)
            preferred_filter = target.get('_missav_filter')
            if preferred_filter:
                sep = '&' if '?' in base_url else '?'
                base_url = f'{base_url}{sep}filters={preferred_filter}'
                cat_name = f'{cat_name} · {T("st_pref_chinese")}'
            if site_name == 'JableTV' and 'sort_by=' not in base_url:
                sep = '&' if '?' in base_url else '?'
                base_url = f'{base_url}{sep}sort_by=post_date'

            max_pages = MAX_SCAN_PAGES if first_run else DAILY_SCAN_PAGES
            reached_baseline = False
            consecutive_skips = 0

            for page in range(1, max_pages + 1):
                if self._stop.is_set():
                    return False
                if reached_baseline:
                    break

                page_url = self._build_page_url(site_name, base_url, page)
                self._set_scan_state(
                    site_name, cat_name, page, len(all_new_videos))
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

                target_id = str(cat.get('id') or target.get('id') or '')
                for video in videos:
                    video['_site'] = site_name
                    video['_target_id'] = target_id
                    video['_category'] = cat_name

                self._log(f'  Page {page}: {len(videos)} video(s)')
                page_all_seen = True

                for v in videos:
                    if self._stop.is_set():
                        return False
                    vurl = v.get('url', '')
                    if not vurl:
                        continue
                    with self._seen_lock:
                        seen_entry = self._seen.get(vurl)
                    if isinstance(seen_entry, dict):
                        known_versions = set(video_versions(v))
                        stored_versions = seen_entry.get('versions', [])
                        if isinstance(stored_versions, str):
                            stored_versions = [stored_versions]
                        if isinstance(stored_versions, (list, tuple, set)):
                            known_versions.update(
                                value for value in stored_versions
                                if value in VALID_VERSION_PREFERENCES)
                        reconsider_preferred = (
                            seen_entry.get('reason') == 'duplicate-version' and
                            version_preference in known_versions)
                        reconsider_older_baseline = False
                        if seen_entry.get('reason') == 'before-baseline':
                            release_date = seen_entry.get('release_date')
                            if release_date:
                                try:
                                    release_dt = datetime.strptime(
                                        release_date, '%Y-%m-%d').replace(
                                            tzinfo=timezone.utc)
                                    reconsider_older_baseline = (
                                        release_dt >= baseline_dt)
                                except (TypeError, ValueError):
                                    reconsider_older_baseline = True
                        if not (reconsider_preferred or
                                reconsider_older_baseline):
                            continue
                    elif seen_entry:
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
                            v['_release_date'] = video_dt.date().isoformat()
                            slug = vurl.rstrip('/').split('/')[-1]
                            self._log(f'    [STOP] {slug} — {rel_text} (before {baseline_str})')
                            self._mark_seen(
                                vurl, v.get('title', ''), skipped=True,
                                reason='before-baseline', video=v)
                            reached_baseline = True
                            break
                        consecutive_skips = 0
                        self._log(f'    [KEEP] {vurl.rstrip("/").split("/")[-1]} — {rel_text}')
                    elif site_name == 'MissAV':
                        # MissAV: fetch detail page for release date.
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
                            v['_release_date'] = video_dt.date().isoformat()
                            slug = vurl.rstrip('/').split('/')[-1]
                            self._log(f'    [SKIP] {slug} — {rel_text} (before {baseline_str})')
                            self._mark_seen(
                                vurl, v.get('title', ''), skipped=True,
                                reason='before-baseline', video=v)
                            consecutive_skips += 1
                            if consecutive_skips >= 10:
                                self._log(f'  10 consecutive skips — moving to next category.')
                                reached_baseline = True
                                break
                            continue
                        consecutive_skips = 0
                        self._log(f'    [KEEP] {vurl.rstrip("/").split("/")[-1]} — {rel_text}')
                    else:
                        # SupJav exposes YYYY/MM/DD directly on each listing card.
                        rel_text = v.get('date', '')
                        video_dt = self._parse_supjav_listing_date(rel_text)
                        if video_dt is None:
                            self._log(f'    [SKIP] no confirmed date ({rel_text!r}): {vurl}')
                            consecutive_skips += 1
                            if consecutive_skips >= 10:
                                self._log('  10 consecutive skips — moving to next category.')
                                reached_baseline = True
                                break
                            continue
                        if video_dt < baseline_dt:
                            v['_release_date'] = video_dt.date().isoformat()
                            slug = vurl.rstrip('/').split('/')[-1]
                            self._log(f'    [SKIP] {slug} — {rel_text} (before {baseline_str})')
                            self._mark_seen(
                                vurl, v.get('title', ''), skipped=True,
                                reason='before-baseline', video=v)
                            consecutive_skips += 1
                            if consecutive_skips >= 10:
                                self._log('  10 consecutive skips — moving to next category.')
                                reached_baseline = True
                                break
                            continue
                        consecutive_skips = 0
                        self._log(f'    [KEEP] {vurl.rstrip("/").split("/")[-1]} — {rel_text}')

                    all_new_videos.append(v)

                self._set_scan_state(
                    site_name, cat_name, page, len(all_new_videos))

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

        candidate_codes = {
            code for code in (video_code(video) for video in all_new_videos)
            if code
        }
        prior_downloads = self._successful_seen_candidates(candidate_codes)
        kept_candidates, dedupe_decisions = dedupe_video_candidates(
            prior_downloads + all_new_videos, version_preference)
        for dropped, kept, code in dedupe_decisions:
            dropped_slug = video_code(dropped) or url_slug(dropped.get('url', ''))
            kept_slug = video_code(kept) or url_slug(kept.get('url', ''))
            self._log(
                f'  [DEDUP] {code}: keep {kept_slug}; skip {dropped_slug} '
                f'(preference: {version_preference})')
            dropped_url = dropped.get('url', '')
            if (not dropped.get('_already_seen') and dropped_url and
                    dropped_url != kept.get('url', '')):
                self._mark_seen(
                    dropped_url, dropped.get('title', ''), skipped=True,
                    reason='duplicate-version', video=dropped)

        all_new_videos = [
            video for video in kept_candidates
            if not video.get('_already_seen')
        ]

        if not all_new_videos:
            self._log('No new videos remain after cross-site deduplication.')
            if scan_blocked or not scan_had_success:
                self._log('[WARN] Scan incomplete — will retry before marking first run done.')
                return False
            cfg['first_run_done'] = True
            cfg['last_check_iso'] = datetime.now(timezone.utc).isoformat()
            save_config(cfg)
            return True

        self._set_scan_state()
        self._set_status('st_downloading', ACCENT)
        self._log(f'Found {len(all_new_videos)} new video(s). Downloading...')
        download_blocked = False
        for v in all_new_videos:
            if self._stop.is_set():
                return False
            if self._download_one(v, dest) == 'blocked':
                download_blocked = True

        if download_blocked:
            self._log('[WARN] Download blocked — will retry before marking first run done.')
            return False
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
                err = getattr(site_obj, '_last_error', None)
                if isinstance(err, MirrorsBlockedError):
                    raise err
                self._log(f'  [SKIP] invalid URL: {vurl}')
                self._mark_seen(vurl, title, skipped=True, video=video)
                return

            # Wire up progress callback for the progress bar
            def _on_progress(done, total, speed):
                with self._progress_lock:
                    self._progress = (done, total, speed, title)

            site_obj._progress_callback = _on_progress
            with self._active_site_lock:
                self._active_site = site_obj
            try:
                ok = site_obj.start_download()
            finally:
                with self._active_site_lock:
                    if self._active_site is site_obj:
                        self._active_site = None
            if ok is False and not getattr(site_obj, '_cancel_job', False):
                self._log('  [ERR] download failed')
                self._cleanup_temp(site_obj)
                return

            if getattr(site_obj, '_cancel_job', False):
                self._log('  [CANCELLED]')
                self._cleanup_temp(site_obj)
                return
            self._log(f'  [OK] {title}')
            self._mark_seen(vurl, title, video=video)
        except MirrorsBlockedError as e:
            self._log(f'  [BLOCKED] {e}')
            if site_obj:
                self._cleanup_temp(site_obj)
            return 'blocked'
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

    def _successful_seen_candidates(self, candidate_codes: set[str]) -> list[dict]:
        """Return successful prior downloads that can collide with this scan."""
        if not candidate_codes:
            return []
        with self._seen_lock:
            seen_items = list(self._seen.items())

        candidates = []
        for url, entry in seen_items:
            if not isinstance(entry, dict) or entry.get('skipped'):
                continue
            candidate = {
                'url': url,
                'title': entry.get('title', ''),
                '_site': entry.get('site') or site_from_url(url),
                '_code': entry.get('code', ''),
                '_versions': entry.get('versions', []),
                '_already_seen': True,
            }
            code = video_code(candidate)
            if code and code in candidate_codes:
                candidate['_code'] = code
                candidates.append(candidate)
        return candidates

    def _mark_seen(self, url: str, title: str, skipped: bool = False,
                   reason: Optional[str] = None,
                   video: Optional[dict] = None):
        with self._seen_lock:
            entry = {
                'title': title,
                'at': datetime.now(timezone.utc).isoformat(),
                'skipped': skipped,
            }
            if reason:
                entry['reason'] = reason
            if video:
                site = video.get('_site') or site_from_url(url)
                code = video_code(video)
                versions = sorted(video_versions(video))
                if site:
                    entry['site'] = site
                if code:
                    entry['code'] = code
                if versions:
                    entry['versions'] = versions
                release_date = video.get('_release_date')
                if release_date:
                    entry['release_date'] = str(release_date)
            self._seen[url] = entry
            save_seen(self._seen)


# ── GUI ──────────────────────────────────────────────────────────────
class SmallToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._lang_code_by_name = {name: code for code, name in LANGUAGES}
        self._lang_name_by_code = {code: name for code, name in LANGUAGES}
        self._theme_mode = config.get_theme()
        ctk.set_appearance_mode(self._theme_mode)
        ctk.set_default_color_theme('blue')

        stored = config.get_ui_lang()
        set_lang(stored or 'en')
        self._needs_lang_prompt = (stored is None)

        self._update_window_title()
        self.geometry('980x800')
        self.minsize(820, 680)
        self.configure(fg_color=BG_DARK)

        self._cfg = load_config()
        self._cfg['resolution'] = _normalize_resolution_pref(self._cfg)
        self._cfg['version_preference'] = _normalize_version_pref(self._cfg)
        self._cfg.pop('missav_version_preference', None)
        from M3U8Sites.M3U8Crawler import set_resolution_pref
        set_resolution_pref(self._cfg['resolution'])
        self._log_queue: list[str] = []
        self._log_lock = threading.Lock()
        self._is_closing = False
        self._rebuilding = False
        self._build_gen = 0
        self._status_key = 'st_idle'
        self._status_fg = TEXT_DIM
        self._worker = SmallToolWorker(log_fn=self._enqueue_log,
                                       status_fn=self._set_status_threadsafe)
        self._check_vars: dict[str, tk.BooleanVar] = {}  # stable "site|target-id" keys
        self._target_widgets: list[tuple[object, str]] = []
        self._filter_groups: list[dict] = []
        self._category_groups: list[list[object]] = []
        self._category_columns = category_columns_for_width(980)
        self._categories_collapsed = False
        self._progress_display_mode = 'idle'
        self._resize_after_id = None

        self._build_ui()
        self.bind('<Configure>', self._on_root_resize, add='+')
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
        popup = None
        try:
            mode = ctk.get_appearance_mode().lower()
            bg = color_for_mode(BG_DARK, mode)
            card = color_for_mode(BG_CARD, mode)
            fg = color_for_mode(TEXT_PRI, mode)
            accent = color_for_mode(ACCENT, mode)
            popup = tk.Toplevel(self)
            popup.title(T('st_lang_picker_title'))
            popup.configure(bg=bg)
            popup.resizable(False, False)
            popup.transient(self)

            picker_font = ui_font()
            tk.Label(
                popup, text=T('st_lang_picker_title'),
                bg=bg, fg=fg,
                font=(picker_font, 14, 'bold')).pack(padx=28, pady=(24, 12))

            def _choose(code='en'):
                config.set_ui_lang(code)
                if code != get_lang():
                    self._apply_language(code)
                try:
                    popup.destroy()
                except tk.TclError:
                    pass

            for code, name in LANGUAGES:
                tk.Button(
                    popup, text=name, width=24,
                    bg=card, fg=fg,
                    activebackground=accent, activeforeground='#ffffff',
                    relief='flat', bd=0, padx=12, pady=8,
                    font=(picker_font, 11),
                    command=lambda c=code: _choose(c)).pack(padx=28, pady=4)

            popup.protocol('WM_DELETE_WINDOW', lambda: _choose(get_lang() or 'en'))
            popup.update_idletasks()
            x = max(0, (popup.winfo_screenwidth() - popup.winfo_width()) // 2)
            y = max(0, (popup.winfo_screenheight() - popup.winfo_height()) // 3)
            popup.geometry(f'+{x}+{y}')
        except Exception:
            if popup is not None:
                try:
                    popup.destroy()
                except tk.TclError:
                    pass
            try:
                config.set_ui_lang('en')
            except Exception:
                pass

    def _first_run_language_prompt(self):
        if getattr(self, '_is_closing', False):
            return
        self._ask_language_first_run()

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
            'resolution': self._cfg.get('resolution', 'highest'),
            'version_preference': self._cfg.get(
                'version_preference', DEFAULT_VERSION_PREFERENCE),
            'running': self._worker.is_running(),
            'check_now_state': check_state,
            'status_key': self._status_key,
            'status_fg': self._status_fg,
            'categories_collapsed': self._categories_collapsed,
        }

    def _restore_ui_state(self, snapshot: dict):
        self._cfg['output_folder'] = snapshot['folder']
        self._cfg['baseline_date'] = snapshot['baseline_date']
        self._cfg['resolution'] = snapshot['resolution']
        self._cfg['version_preference'] = snapshot['version_preference']
        from M3U8Sites.M3U8Crawler import set_resolution_pref
        set_resolution_pref(snapshot['resolution'])
        self._folder_var.set(snapshot['folder'])
        self._date_var.set(snapshot['baseline_date'])
        self._res_var.set(self._resolution_label())
        self._version_var.set(self._version_label())

        for var in self._check_vars.values():
            var.set(False)
        self._restore_target_checks(snapshot['selected_targets'])
        self._sync_select_all_vars()

        running = snapshot['running']
        self._start_btn.configure(state='disabled' if running else 'normal')
        self._stop_btn.configure(state='normal' if running else 'disabled')
        if running and snapshot['status_key'] in ('st_idle', 'st_stopped'):
            self._set_status_key('st_running', SUCCESS)
        else:
            self._set_status_key(snapshot['status_key'], snapshot['status_fg'])
        self._check_now_btn.configure(state=snapshot['check_now_state'])
        self._set_categories_collapsed(snapshot['categories_collapsed'])

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
            self._target_widgets = []
            self._filter_groups = []
            self._category_groups = []
            self._build_ui()
            self._restore_ui_state(snapshot)
            self._update_window_title()
        finally:
            self._rebuilding = False

    def _resolution_label(self) -> str:
        pref = self._cfg.get('resolution', 'highest')
        if pref == 'lowest':
            return T('st_resolution_lowest')
        if pref in {'1080', '720', '480', '360'}:
            return f'{pref}p'
        return T('st_resolution_highest')

    def _resolution_values(self) -> list[str]:
        return [T('st_resolution_highest'), '1080p', '720p', '480p', '360p',
                T('st_resolution_lowest')]

    def _resolution_pref_from_label(self, label) -> str:
        label = str(label or '').strip()
        if label == T('st_resolution_lowest'):
            return 'lowest'
        if label in {'1080p', '720p', '480p', '360p'}:
            return label[:-1]
        return 'highest'

    def _version_label(self) -> str:
        pref = self._cfg.get('version_preference', DEFAULT_VERSION_PREFERENCE)
        return {
            'chinese-subtitle': T('st_pref_chinese'),
            'uncensored': T('st_pref_uncensored'),
            'standard': T('st_pref_standard'),
            'english-subtitle': T('st_pref_english'),
            'reducing-mosaic': T('st_pref_reducing_mosaic'),
        }.get(pref, T('st_pref_chinese'))

    def _version_values(self) -> list[str]:
        return [
            T('st_pref_chinese'),
            T('st_pref_uncensored'),
            T('st_pref_standard'),
            T('st_pref_english'),
            T('st_pref_reducing_mosaic'),
        ]

    def _version_pref_from_label(self, label: str) -> str:
        return {
            T('st_pref_chinese'): 'chinese-subtitle',
            T('st_pref_uncensored'): 'uncensored',
            T('st_pref_standard'): 'standard',
            T('st_pref_english'): 'english-subtitle',
            T('st_pref_reducing_mosaic'): 'reducing-mosaic',
        }.get(str(label or ''), DEFAULT_VERSION_PREFERENCE)

    def _set_status_key(self, key: str, fg: str = TEXT_DIM):
        self._status_key = key
        self._status_fg = fg
        text = T(key) if key.startswith('st_') else key
        if hasattr(self, '_status_lbl'):
            try:
                self._status_lbl.configure(text=text, text_color=fg)
            except tk.TclError:
                pass

    def _theme_glyph(self):
        return {'system': '◐', 'light': '☀', 'dark': '☾'}.get(self._theme_mode, '◐')

    def _cycle_theme(self):
        modes = ('system', 'light', 'dark')
        try:
            index = modes.index(self._theme_mode)
        except ValueError:
            index = 0
        self._theme_mode = modes[(index + 1) % len(modes)]
        ctk.set_appearance_mode(self._theme_mode)
        config.set_theme(self._theme_mode)
        self._theme_btn.configure(text=self._theme_glyph())

    def _on_root_resize(self, event):
        if event.widget is not self or self._is_closing:
            return
        try:
            logical_width = event.width / max(self._get_window_scaling(), 1.0)
        except Exception:
            logical_width = event.width
        columns = category_columns_for_width(logical_width)
        if columns == self._category_columns:
            return
        self._category_columns = columns
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        try:
            self._resize_after_id = self.after(160, self._reflow_category_grid)
        except tk.TclError:
            self._resize_after_id = None

    def _reflow_category_grid(self):
        self._resize_after_id = None
        for widgets in self._category_groups:
            for index, widget in enumerate(widgets):
                try:
                    widget.grid_configure(
                        row=index // self._category_columns,
                        column=index % self._category_columns)
                except tk.TclError:
                    pass
        if hasattr(self, '_category_filter_var'):
            self._filter_targets()

    def _build_ui(self):
        font_family = ui_font()
        self._update_window_title()

        # ── Header ──────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=BG_HEADER, corner_radius=0, height=72)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        brand = ctk.CTkFrame(hdr, fg_color='transparent')
        brand.pack(side='left', fill='y', padx=20)
        ctk.CTkLabel(
            brand, text=T('st_header'), text_color=TEXT_PRI,
            font=(font_family, 17, 'bold')).pack(anchor='w', pady=(10, 0))
        ctk.CTkLabel(
            brand, text=T('st_subtitle').upper(), text_color=ACCENT,
            font=('Consolas', 9, 'bold')).pack(anchor='w', pady=(0, 10))

        right_info = ctk.CTkFrame(hdr, fg_color='transparent')
        right_info.pack(side='right', fill='y', padx=20)

        version_box = ctk.CTkFrame(
            right_info, fg_color=BG_BADGE, corner_radius=6,
            border_width=1, border_color=BORDER)
        version_box.pack(side='right', padx=(10, 0), pady=18)
        ctk.CTkLabel(
            version_box, text=f'v{APP_VERSION}', text_color=TEXT_SEC,
            font=('Consolas', 10, 'bold')).pack(padx=10, pady=4)

        self._theme_btn = ctk.CTkButton(
            right_info, text=self._theme_glyph(), width=36, height=36,
            corner_radius=CONTROL_RADIUS, fg_color=BG_CARD,
            border_width=1, border_color=BORDER,
            hover_color=BG_CARD_HOVER, text_color=TEXT_SEC,
            font=(font_family, 14), command=self._cycle_theme)
        self._theme_btn.pack(side='right', padx=(8, 0), pady=18)

        self._lang_var = ctk.StringVar(
            value=self._lang_name_by_code.get(get_lang(), 'English'))
        self._lang_menu = ctk.CTkOptionMenu(
            right_info, values=[name for _, name in LANGUAGES],
            variable=self._lang_var, command=self._on_lang_change,
            width=126, height=36, corner_radius=CONTROL_RADIUS,
            fg_color=BG_INPUT, button_color=BORDER_HOVER,
            button_hover_color=ACCENT, text_color=TEXT_PRI,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_CARD_HOVER,
            dropdown_text_color=TEXT_PRI,
            font=(font_family, 11), dropdown_font=(font_family, 11))
        self._lang_menu.pack(side='right', pady=18)

        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(fill='x')

        main = ctk.CTkFrame(self, fg_color='transparent')
        main.pack(fill='both', expand=True, padx=18, pady=(14, 12))

        # ── Config row: folder + date ───────────────────────────────
        cfg_card = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=CARD_RADIUS,
            border_width=1, border_color=BORDER_CARD)
        cfg_card.pack(fill='x')
        cfg_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            cfg_card, text=T('st_save_location'), text_color=TEXT_SEC,
            font=(font_family, 11, 'bold'), width=98, anchor='w').grid(
                row=0, column=0, padx=(16, 8), pady=(14, 8), sticky='w')
        self._folder_var = tk.StringVar(
            value=self._cfg.get('output_folder') or _default_output_folder())
        ctk.CTkEntry(
            cfg_card, textvariable=self._folder_var, height=38,
            corner_radius=CONTROL_RADIUS, fg_color=BG_INPUT,
            border_color=BORDER, border_width=1,
            text_color=TEXT_PRI, font=(font_family, 11)).grid(
                row=0, column=1, padx=8, pady=(14, 8), sticky='ew')
        ctk.CTkButton(
            cfg_card, text=T('st_browse'), width=82, height=38,
            corner_radius=CONTROL_RADIUS, fg_color='transparent',
            border_width=1, border_color=BORDER_HOVER,
            hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
            font=(font_family, 11), command=self._pick_folder).grid(
                row=0, column=2, padx=(8, 16), pady=(14, 8))

        ctk.CTkLabel(
            cfg_card, text=T('proxy_url_label'), text_color=TEXT_SEC,
            font=(font_family, 11, 'bold'), width=98, anchor='w').grid(
                row=1, column=0, padx=(16, 8), pady=(2, 2), sticky='w')
        self._proxy_var = tk.StringVar(value=config.get_proxy_url())
        ctk.CTkEntry(
            cfg_card, textvariable=self._proxy_var,
            placeholder_text=T('proxy_url_placeholder'), height=34,
            corner_radius=CONTROL_RADIUS, fg_color=BG_INPUT,
            border_color=BORDER, border_width=1,
            text_color=TEXT_PRI, font=(font_family, 10)).grid(
                row=1, column=1, padx=8, pady=(2, 2), sticky='ew')
        proxy_actions = ctk.CTkFrame(cfg_card, fg_color='transparent')
        proxy_actions.grid(row=1, column=2, padx=(8, 16), pady=(2, 2))
        ctk.CTkButton(
            proxy_actions, text=T('proxy_save'), width=62, height=34,
            corner_radius=CONTROL_RADIUS, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=WHITE,
            font=(font_family, 9, 'bold'), command=self._on_proxy_save).pack(
                side='left')
        ctk.CTkButton(
            proxy_actions, text=T('proxy_clear'), width=62, height=34,
            corner_radius=CONTROL_RADIUS, fg_color='transparent',
            border_width=1, border_color=BORDER_HOVER,
            hover_color=BG_CARD_HOVER, text_color=TEXT_SEC,
            font=(font_family, 9), command=self._on_proxy_clear).pack(
                side='left', padx=(6, 0))

        self._proxy_status_lbl = ctk.CTkLabel(
            cfg_card, text='', text_color=TEXT_DIM,
            font=(font_family, 9), anchor='w')
        self._proxy_status_lbl.grid(
            row=2, column=1, columnspan=2, padx=8, pady=(0, 4), sticky='w')
        self._refresh_proxy_status()

        options = ctk.CTkFrame(cfg_card, fg_color='transparent')
        options.grid(row=3, column=0, columnspan=3, padx=16, pady=(2, 14), sticky='ew')

        date_group = ctk.CTkFrame(options, fg_color='transparent')
        date_group.pack(side='left', fill='x', expand=True)
        date_controls = ctk.CTkFrame(date_group, fg_color='transparent')
        date_controls.pack(fill='x')
        ctk.CTkLabel(
            date_controls, text=T('st_baseline_date'), text_color=TEXT_SEC,
            font=(font_family, 10, 'bold')).pack(side='left')
        self._date_var = tk.StringVar(value=self._cfg.get('baseline_date', DEFAULT_BASELINE_DATE))
        ctk.CTkEntry(
            date_controls, textvariable=self._date_var, width=116, height=34,
            corner_radius=CONTROL_RADIUS, fg_color=BG_INPUT,
            border_color=BORDER, border_width=1,
            text_color=TEXT_PRI, font=('Consolas', 10)).pack(
                side='left', padx=(8, 6))
        ctk.CTkButton(
            date_controls, text=T('st_calendar'), width=82, height=34,
            corner_radius=CONTROL_RADIUS, fg_color='transparent',
            border_width=1, border_color=BORDER_HOVER,
            hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
            font=(font_family, 9, 'bold'), command=self._open_calendar).pack(
                side='left', padx=(0, 6))
        self._date_preset_var = tk.StringVar(value=T('st_date_quick'))
        ctk.CTkOptionMenu(
            date_controls, variable=self._date_preset_var,
            values=[label for label, _kind, _amount in self._date_presets()],
            command=self._on_date_preset, width=132, height=34,
            corner_radius=CONTROL_RADIUS, fg_color=BG_INPUT,
            button_color=BORDER_HOVER, button_hover_color=ACCENT,
            text_color=TEXT_PRI, dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_CARD_HOVER,
            dropdown_text_color=TEXT_PRI,
            font=(font_family, 9), dropdown_font=(font_family, 9)).pack(
                side='left')
        ctk.CTkLabel(
            date_group, text=T('st_date_hint'), text_color=TEXT_DIM,
            font=(font_family, 9), wraplength=440, justify='left').pack(
                anchor='w', pady=(4, 0))

        res_group = ctk.CTkFrame(options, fg_color='transparent')
        res_group.pack(side='right', padx=(16, 0))
        quality_row = ctk.CTkFrame(res_group, fg_color='transparent')
        quality_row.pack(fill='x')
        ctk.CTkLabel(
            quality_row, text=T('st_resolution'), text_color=TEXT_SEC,
            font=(font_family, 10, 'bold'), width=108, anchor='e').pack(
                side='left', padx=(0, 8))
        self._res_var = tk.StringVar(value=self._resolution_label())
        ctk.CTkOptionMenu(
            quality_row, variable=self._res_var, values=self._resolution_values(),
            command=self._on_res_change, width=178, height=34,
            corner_radius=CONTROL_RADIUS, fg_color=BG_INPUT,
            button_color=BORDER_HOVER, button_hover_color=ACCENT,
            text_color=TEXT_PRI, dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_CARD_HOVER,
            dropdown_text_color=TEXT_PRI,
            font=(font_family, 10), dropdown_font=(font_family, 10)).pack(side='left')

        version_row = ctk.CTkFrame(res_group, fg_color='transparent')
        version_row.pack(fill='x', pady=(6, 0))
        ctk.CTkLabel(
            version_row, text=T('st_version_preference'), text_color=TEXT_SEC,
            font=(font_family, 10, 'bold'), width=108, anchor='e').pack(
                side='left', padx=(0, 8))
        self._version_var = tk.StringVar(value=self._version_label())
        ctk.CTkOptionMenu(
            version_row, variable=self._version_var,
            values=self._version_values(),
            command=self._on_version_change, width=178, height=34,
            corner_radius=CONTROL_RADIUS, fg_color=BG_INPUT,
            button_color=BORDER_HOVER, button_hover_color=ACCENT,
            text_color=TEXT_PRI, dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_CARD_HOVER,
            dropdown_text_color=TEXT_PRI,
            font=(font_family, 10), dropdown_font=(font_family, 10)).pack(
                side='left')
        # Apply saved preference immediately (before auto-start)
        from M3U8Sites.M3U8Crawler import set_resolution_pref
        set_resolution_pref(self._cfg.get('resolution', 'highest'))

        # ── Site / Category selection ───────────────────────────────
        selection = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=CARD_RADIUS,
            border_width=1, border_color=BORDER_CARD)
        selection.pack(fill='both', expand=True, pady=(12, 10))
        self._selection_panel = selection

        selection_header = ctk.CTkFrame(selection, fg_color='transparent')
        selection_header.pack(fill='x', padx=16, pady=(14, 8))
        ctk.CTkLabel(
            selection_header, text=T('st_select_hint'), text_color=TEXT_PRI,
            font=(font_family, 13, 'bold')).pack(side='left')
        self._selected_count_lbl = ctk.CTkLabel(
            selection_header, text=f'0 {T("selected")}', text_color=TEXT_DIM,
            font=(font_family, 10, 'bold'))
        self._selected_count_lbl.pack(side='left', padx=(10, 0))

        self._categories_toggle_btn = ctk.CTkButton(
            selection_header, text=T('st_categories_collapse'),
            width=104, height=32, corner_radius=CONTROL_RADIUS,
            fg_color='transparent', hover_color=BG_CARD_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SEC, font=(font_family, 9, 'bold'),
            command=self._toggle_categories)
        self._categories_toggle_btn.pack(side='right')

        self._category_filter_box = ctk.CTkFrame(
            selection_header, fg_color='transparent')
        self._category_filter_box.pack(side='right', padx=(0, 8))
        ctk.CTkLabel(
            self._category_filter_box, text=T('st_filter_categories'),
            text_color=TEXT_DIM, font=(font_family, 9)).pack(
                side='left', padx=(0, 8))
        self._category_filter_var = tk.StringVar()
        filter_entry = ctk.CTkEntry(
            self._category_filter_box, textvariable=self._category_filter_var,
            width=190, height=32,
            corner_radius=CONTROL_RADIUS, fg_color=BG_INPUT,
            border_color=BORDER, border_width=1,
            text_color=TEXT_PRI, font=(font_family, 10))
        filter_entry.pack(side='left')
        self._category_filter_var.trace_add('write', self._filter_targets)

        tabview = ctk.CTkTabview(
            selection, fg_color='transparent', corner_radius=0,
            segmented_button_fg_color=BG_INPUT,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=BG_INPUT,
            segmented_button_unselected_hover_color=BG_CARD_HOVER,
            text_color=TEXT_PRI, border_width=0)
        tabview.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self._category_tabview = tabview

        for site_name, site_info in SITES.items():
            tab_name = f'{site_name}  {len(list(iter_targets(site_name)))}'
            tabview.add(tab_name)
            tab = tabview.tab(tab_name)
            tab.configure(fg_color='transparent')
            inner = ctk.CTkScrollableFrame(
                tab, fg_color='transparent', corner_radius=0,
                scrollbar_button_color=BORDER,
                scrollbar_button_hover_color=BORDER_HOVER)
            inner.pack(fill='both', expand=True)

            for group in site_info['groups']:
                group_frame = ctk.CTkFrame(
                    inner, fg_color=BG_SECTION, corner_radius=8,
                    border_width=1, border_color=BORDER_CARD)
                group_frame.pack(fill='x', padx=4, pady=5)

                group_header = ctk.CTkFrame(group_frame, fg_color='transparent')
                group_header.pack(fill='x', padx=12, pady=(9, 5))
                ctk.CTkLabel(
                    group_header,
                    text=f'{group_label(group)}  {len(group["targets"])}',
                    text_color=TEXT_PRI, font=(font_family, 11, 'bold')).pack(
                        side='left')

                all_key = f'{site_name}|__group__|{group["id"]}'
                all_var = tk.BooleanVar(value=False)
                self._check_vars[all_key] = all_var
                ctk.CTkCheckBox(
                    group_header, text=T('st_select_all'), variable=all_var,
                    width=110, height=24, checkbox_width=18, checkbox_height=18,
                    corner_radius=4, border_width=1,
                    fg_color=ACCENT, hover_color=ACCENT_HOVER,
                    border_color=BORDER_HOVER, checkmark_color=WHITE,
                    text_color=ACCENT, font=(font_family, 10, 'bold'),
                    command=lambda sn=site_name, gid=group['id']:
                        self._toggle_select_group(sn, gid),
                ).pack(side='right')

                cat_grid = ctk.CTkFrame(group_frame, fg_color='transparent')
                cat_grid.pack(fill='x', padx=10, pady=(0, 10))
                for col in range(3):
                    cat_grid.grid_columnconfigure(col, weight=1)
                group_widgets = []
                filter_items = []
                for i, target in enumerate(group['targets']):
                    label = target_label(target)
                    key = selection_key(site_name, target['id'])
                    var = tk.BooleanVar(value=False)
                    self._check_vars[key] = var
                    cb = ctk.CTkCheckBox(
                        cat_grid, text=label, variable=var,
                        height=26, checkbox_width=17, checkbox_height=17,
                        corner_radius=4, border_width=1,
                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        border_color=BORDER_HOVER, checkmark_color=WHITE,
                        text_color=TEXT_SEC, font=(font_family, 10),
                        command=lambda sn=site_name, gid=group['id']:
                            self._sync_group_select(sn, gid))
                    row, col = divmod(i, self._category_columns)
                    cb.grid(row=row, column=col, sticky='w', padx=6, pady=3)
                    self._target_widgets.append((cb, label.casefold()))
                    group_widgets.append(cb)
                    filter_items.append((cb, label.casefold()))
                self._category_groups.append(group_widgets)
                self._filter_groups.append({
                    'frame': group_frame,
                    'items': filter_items,
                })

        # ── Control row ─────────────────────────────────────────────
        ctrl = ctk.CTkFrame(main, fg_color='transparent')
        ctrl.pack(fill='x', pady=(0, 10))

        self._start_btn = ctk.CTkButton(
            ctrl, text=T('st_start'), width=142, height=40,
            corner_radius=CONTROL_RADIUS, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=WHITE,
            font=(font_family, 11, 'bold'),
            command=self._start_worker)
        self._start_btn.pack(side='left')

        self._stop_btn = ctk.CTkButton(
            ctrl, text=T('st_stop'), width=92, height=40,
            corner_radius=CONTROL_RADIUS, fg_color=ERROR_DIM,
            hover_color=BG_CARD_HOVER, text_color=ERROR_C,
            border_width=1, border_color=BORDER,
            font=(font_family, 11),
            command=self._stop_worker,
            state='disabled')
        self._stop_btn.pack(side='left', padx=(8, 0))

        self._check_now_btn = ctk.CTkButton(
            ctrl, text=T('st_check_now'), width=112, height=40,
            corner_radius=CONTROL_RADIUS, fg_color='transparent',
            border_width=1, border_color=BORDER_HOVER,
            hover_color=BG_CARD_HOVER, text_color=TEXT_PRI,
            font=(font_family, 11),
            command=self._check_now)
        self._check_now_btn.pack(side='left', padx=(8, 0))

        status_box = ctk.CTkFrame(
            ctrl, fg_color=BG_BADGE, corner_radius=CONTROL_RADIUS,
            border_width=1, border_color=BORDER)
        status_box.pack(side='right')
        self._status_lbl = ctk.CTkLabel(
            status_box, text=T(self._status_key), text_color=self._status_fg,
            font=(font_family, 10, 'bold'))
        self._status_lbl.pack(padx=12, pady=6)

        # ── Download progress bar ───────────────────────────────────
        prog_outer = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=CARD_RADIUS,
            border_width=1, border_color=BORDER_CARD)
        prog_outer.pack(fill='x', pady=(0, 10))

        self._prog_title = ctk.CTkLabel(
            prog_outer, text=T('st_progress_idle'), text_color=TEXT_SEC,
            font=(font_family, 10, 'bold'), anchor='w')
        self._prog_title.pack(fill='x', padx=14, pady=(10, 4))

        bar_row = ctk.CTkFrame(prog_outer, fg_color='transparent')
        bar_row.pack(fill='x', padx=14, pady=(0, 10))

        self._prog_bar = ctk.CTkProgressBar(
            bar_row, height=8, corner_radius=4,
            fg_color=BG_INPUT, progress_color=ACCENT)
        self._prog_bar.set(0)
        self._prog_bar.pack(side='left', fill='x', expand=True, pady=7)
        self._progress_display_mode = 'idle'

        self._prog_pct = ctk.CTkLabel(
            bar_row, text='', text_color=ACCENT,
            font=('Consolas', 10, 'bold'), width=48, anchor='e')
        self._prog_pct.pack(side='left', padx=(8, 0))

        self._prog_info = ctk.CTkLabel(
            bar_row, text='', text_color=TEXT_SEC,
            font=('Consolas', 9), anchor='e')
        self._prog_info.pack(side='right', padx=(8, 0))

        # ── Log box ─────────────────────────────────────────────────
        activity = ctk.CTkFrame(
            main, fg_color=BG_CARD, corner_radius=CARD_RADIUS,
            border_width=1, border_color=BORDER_CARD)
        activity.pack(fill='both', expand=True)
        activity_header = ctk.CTkFrame(activity, fg_color='transparent')
        activity_header.pack(fill='x', padx=14, pady=(9, 5))
        ctk.CTkLabel(
            activity_header, text=T('st_activity'), text_color=TEXT_PRI,
            font=(font_family, 11, 'bold')).pack(side='left')
        ctk.CTkLabel(
            activity_header, text=T('st_footer_short'), text_color=TEXT_DIM,
            font=(font_family, 9)).pack(side='right')

        self._log_box = ctk.CTkTextbox(
            activity, fg_color=BG_INPUT, text_color=TEXT_SEC,
            border_width=0, corner_radius=6,
            font=('Consolas', 10), wrap='word', state='disabled')
        self._log_box.pack(fill='both', expand=True, padx=10, pady=(0, 10))

    # ── Selection helpers ────────────────────────────────────────────
    def _toggle_categories(self):
        self._set_categories_collapsed(not self._categories_collapsed)

    def _set_categories_collapsed(self, collapsed: bool):
        if not all(hasattr(self, name) for name in (
                '_selection_panel', '_category_tabview',
                '_category_filter_box', '_categories_toggle_btn')):
            return
        self._categories_collapsed = bool(collapsed)
        if self._categories_collapsed:
            self._category_filter_box.pack_forget()
            self._category_tabview.pack_forget()
            self._selection_panel.pack_configure(fill='x', expand=False)
            button_text = T('st_categories_expand')
        else:
            self._category_filter_box.pack(side='right', padx=(0, 8))
            self._category_tabview.pack(
                fill='both', expand=True, padx=10, pady=(0, 10))
            self._selection_panel.pack_configure(fill='both', expand=True)
            button_text = T('st_categories_collapse')
        self._categories_toggle_btn.configure(text=button_text)

    def _update_selected_count(self):
        if not hasattr(self, '_selected_count_lbl'):
            return
        count = sum(
            1 for key, var in self._check_vars.items()
            if '|__group__|' not in key and var.get())
        self._selected_count_lbl.configure(
            text=f'{count} {T("selected")}',
            text_color=ACCENT if count else TEXT_DIM)

    def _filter_targets(self, *_args):
        query = self._category_filter_var.get().strip().casefold()
        visibility = []
        for group in self._filter_groups:
            group_matches = False
            for widget, label in group['items']:
                try:
                    matches = not query or query in label
                    if matches:
                        widget.grid()
                        group_matches = True
                    else:
                        widget.grid_remove()
                except tk.TclError:
                    pass
            visibility.append((group, group_matches))

        # Repack in registry order so empty groups do not leave large blank areas.
        for group, _matches in visibility:
            try:
                group['frame'].pack_forget()
            except tk.TclError:
                pass
        for group, matches in visibility:
            if not matches:
                continue
            try:
                group['frame'].pack(fill='x', padx=4, pady=5)
            except tk.TclError:
                pass

    def _toggle_select_group(self, site_name: str, group_id: str):
        all_key = f'{site_name}|__group__|{group_id}'
        val = self._check_vars[all_key].get()
        group = next(g for g in SITES[site_name]['groups'] if g['id'] == group_id)
        for target in group['targets']:
            self._check_vars[selection_key(site_name, target['id'])].set(val)
        self._update_selected_count()

    def _sync_group_select(self, site_name: str, group_id: str):
        group = next(g for g in SITES[site_name]['groups'] if g['id'] == group_id)
        all_key = f'{site_name}|__group__|{group_id}'
        target_keys = [selection_key(site_name, target['id'])
                       for target in group['targets']]
        self._check_vars[all_key].set(
            bool(target_keys) and
            all(self._check_vars[key].get() for key in target_keys))
        self._update_selected_count()

    def _sync_select_all_vars(self):
        for site_name, site_info in SITES.items():
            for group in site_info['groups']:
                all_key = f'{site_name}|__group__|{group["id"]}'
                if all_key in self._check_vars:
                    self._sync_group_select(site_name, group['id'])
        self._update_selected_count()

    def _get_selected_targets(self) -> list[dict]:
        targets = []
        for site_name in SITES:
            for target in iter_targets(site_name):
                key = selection_key(site_name, target['id'])
                var = self._check_vars.get(key)
                if var is not None and var.get():
                    targets.append({
                        'site': site_name,
                        'id': target['id'],
                        'category': target['name'],
                    })
        return targets

    def _date_presets(self):
        return [
            (T('st_date_yesterday'), 'days', 1),
            (T('st_date_month_1'), 'months', 1),
            (T('st_date_month_2'), 'months', 2),
            (T('st_date_month_3'), 'months', 3),
            (T('st_date_month_6'), 'months', 6),
        ]

    def _on_date_preset(self, selected_label: str):
        today = datetime.now().astimezone().date()
        for label, kind, amount in self._date_presets():
            if label != selected_label:
                continue
            selected = (today - timedelta(days=amount)
                        if kind == 'days' else _months_before(today, amount))
            self._date_var.set(selected.isoformat())
            return

    def _open_calendar(self):
        existing = getattr(self, '_calendar_popup', None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.focus_force()
                return
        except tk.TclError:
            pass

        today = datetime.now().astimezone().date()
        try:
            selected = datetime.strptime(
                self._date_var.get().strip(), '%Y-%m-%d').date()
        except ValueError:
            selected = today

        popup = ctk.CTkToplevel(self)
        self._calendar_popup = popup
        popup.title(T('st_calendar_title'))
        popup.geometry('364x448')
        popup.resizable(False, False)
        popup.transient(self)
        popup.configure(fg_color=BG_DARK)
        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(1, weight=1)

        view_month = [selected.replace(day=1)]

        def close_popup():
            try:
                popup.grab_release()
            except tk.TclError:
                pass
            try:
                popup.destroy()
            except tk.TclError:
                pass
            self._calendar_popup = None

        def choose_day(day_value: date):
            self._date_var.set(day_value.isoformat())
            close_popup()

        header = ctk.CTkFrame(popup, fg_color=BG_CARD, corner_radius=0)
        header.grid(row=0, column=0, sticky='ew')
        header.grid_columnconfigure(1, weight=1)
        month_label = ctk.CTkLabel(
            header, text='', text_color=TEXT_PRI,
            font=(ui_font(), 14, 'bold'))
        ctk.CTkButton(
            header, text='‹', width=44, height=40,
            fg_color='transparent', hover_color=BG_CARD_HOVER,
            text_color=TEXT_PRI, font=(ui_font(), 20, 'bold'),
            command=lambda: shift_month(-1)).grid(
                row=0, column=0, padx=(12, 4), pady=10)
        month_label.grid(row=0, column=1, padx=4, pady=10)
        ctk.CTkButton(
            header, text='›', width=44, height=40,
            fg_color='transparent', hover_color=BG_CARD_HOVER,
            text_color=TEXT_PRI, font=(ui_font(), 20, 'bold'),
            command=lambda: shift_month(1)).grid(
                row=0, column=2, padx=(4, 12), pady=10)

        grid = ctk.CTkFrame(
            popup, fg_color=BG_CARD, corner_radius=CARD_RADIUS,
            border_width=1, border_color=BORDER_CARD)
        grid.grid(row=1, column=0, padx=14, pady=14, sticky='nsew')
        for column in range(7):
            grid.grid_columnconfigure(column, weight=1)

        def render_month():
            for child in grid.winfo_children():
                child.destroy()
            current = view_month[0]
            month_label.configure(text=f'{current.year} / {current.month:02d}')
            weekdays = T('st_weekdays').split('|')
            if len(weekdays) != 7:
                weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            for column, weekday in enumerate(weekdays):
                ctk.CTkLabel(
                    grid, text=weekday, text_color=TEXT_DIM,
                    font=(ui_font(), 9, 'bold')).grid(
                        row=0, column=column, padx=2, pady=(10, 6))

            weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(
                current.year, current.month)
            for row, week in enumerate(weeks, start=1):
                for column, day_number in enumerate(week):
                    if day_number == 0:
                        ctk.CTkLabel(grid, text='', width=38, height=34).grid(
                            row=row, column=column, padx=2, pady=2)
                        continue
                    day_value = date(current.year, current.month, day_number)
                    is_selected = day_value == selected
                    is_today = day_value == today
                    ctk.CTkButton(
                        grid, text=str(day_number), width=38, height=34,
                        corner_radius=9,
                        fg_color=ACCENT if is_selected else 'transparent',
                        hover_color=ACCENT_HOVER,
                        text_color=WHITE if is_selected else TEXT_PRI,
                        border_width=1 if is_today and not is_selected else 0,
                        border_color=ACCENT,
                        font=(ui_font(), 10, 'bold' if is_selected else 'normal'),
                        command=lambda value=day_value: choose_day(value)).grid(
                            row=row, column=column, padx=2, pady=2)

        def shift_month(delta: int):
            current = view_month[0]
            month_index = current.year * 12 + current.month - 1 + delta
            year, month_zero = divmod(month_index, 12)
            view_month[0] = date(year, month_zero + 1, 1)
            render_month()

        footer = ctk.CTkFrame(popup, fg_color='transparent')
        footer.grid(row=2, column=0, padx=14, pady=(0, 14), sticky='ew')
        ctk.CTkButton(
            footer, text=T('st_date_today'), height=36,
            corner_radius=CONTROL_RADIUS, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=WHITE,
            font=(ui_font(), 10, 'bold'),
            command=lambda: choose_day(today)).pack(side='left', expand=True, fill='x')
        ctk.CTkButton(
            footer, text=T('st_calendar_cancel'), height=36,
            corner_radius=CONTROL_RADIUS, fg_color='transparent',
            border_width=1, border_color=BORDER,
            hover_color=BG_CARD_HOVER, text_color=TEXT_SEC,
            font=(ui_font(), 10), command=close_popup).pack(
                side='left', expand=True, fill='x', padx=(8, 0))

        popup.protocol('WM_DELETE_WINDOW', close_popup)
        render_month()
        popup.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - popup.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - popup.winfo_height()) // 3)
        popup.geometry(f'+{x}+{y}')
        popup.after(40, popup.grab_set)

    def _restore_target_checks(self, targets):
        for saved in targets:
            site_name = saved.get('site')
            if site_name not in SITES:
                continue
            target = find_target(site_name, saved.get('id'), saved.get('category'))
            if not target:
                continue
            key = selection_key(site_name, target['id'])
            if key in self._check_vars:
                self._check_vars[key].set(True)

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
        self._restore_target_checks(self._cfg.get('selected_targets', []))

    # ── Handlers ─────────────────────────────────────────────────────
    def _pick_folder(self):
        d = filedialog.askdirectory(title=T('st_choose_folder'))
        if d:
            self._folder_var.set(d)
            self._cfg['output_folder'] = d
            save_config(self._cfg)
            self._log(T('st_folder_set', path=d))

    def _prepare_output_folder(self) -> Optional[str]:
        folder = self._folder_var.get().strip() or _default_output_folder()
        self._folder_var.set(folder)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                T('st_folder_error'),
                T('st_folder_error_msg', path=folder, error=str(exc)))
            return None
        self._cfg['output_folder'] = folder
        return folder

    def _refresh_proxy_status(self, saved=False):
        enabled = bool(config.get_proxy_url())
        text = T('proxy_enabled') if enabled else T('proxy_disabled')
        if saved:
            text = f"{T('proxy_saved')} · {text}"
        self._proxy_status_lbl.configure(
            text=text, text_color=SUCCESS if enabled else TEXT_DIM)

    def _on_proxy_save(self):
        try:
            value = config.set_proxy_url(self._proxy_var.get())
        except (OSError, ValueError):
            self._proxy_status_lbl.configure(
                text=T('proxy_invalid'), text_color=ERROR_C)
            return
        self._proxy_var.set(value)
        self._refresh_proxy_status(saved=True)

    def _on_proxy_clear(self):
        try:
            config.set_proxy_url('')
        except OSError:
            self._proxy_status_lbl.configure(
                text=T('proxy_invalid'), text_color=ERROR_C)
            return
        self._proxy_var.set('')
        self._refresh_proxy_status()

    def _on_res_change(self, val):
        from M3U8Sites.M3U8Crawler import set_resolution_pref
        pref = self._resolution_pref_from_label(val)
        set_resolution_pref(pref)
        self._cfg['resolution'] = pref
        save_config(self._cfg)

    def _on_version_change(self, val):
        pref = self._version_pref_from_label(val)
        self._cfg['version_preference'] = pref
        self._cfg.pop('missav_version_preference', None)
        save_config(self._cfg)

    def _start_worker(self):
        folder = self._prepare_output_folder()
        if not folder:
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
        cat_names = []
        for saved in targets:
            target = find_target(saved['site'], saved.get('id'), saved.get('category'))
            cat_names.append(target_label(target) if target else saved.get('category', '?'))
        cats_summary = ', '.join(cat_names[:12])
        if len(cat_names) > 12:
            cats_summary += f' … (+{len(cat_names) - 12})'
        self._log(T('st_target_log', sites=sites_summary, categories=cats_summary))
        self._log(T('st_baseline_log', date=date_str))

        self._worker.start()
        self._start_btn.configure(state='disabled')
        self._stop_btn.configure(state='normal')
        self._set_categories_collapsed(True)
        self._set_status_key('st_scanning', ACCENT)
        self._log(T('st_started_msg'))

    def _stop_worker(self):
        self._worker.stop()
        self._worker.cancel_active_download()
        self._start_btn.configure(state='normal')
        self._stop_btn.configure(state='disabled')
        self._set_status_key('st_stopped', TEXT_DIM)

    def _check_now(self):
        if self._worker.is_running():
            self._log(T('st_scan_running'))
            return
        folder = self._prepare_output_folder()
        if not folder:
            return
        targets = self._get_selected_targets()
        if not targets:
            messagebox.showwarning(T('st_no_cat'), T('st_no_cat_msg'))
            return
        date_str = self._validate_baseline_date()
        if not date_str:
            return
        self._cfg['output_folder'] = folder
        if not self._save_selections_to_config(date_str):
            return
        self._check_now_btn.configure(state='disabled')
        self._set_categories_collapsed(True)
        self._set_status_key('st_scanning', ACCENT)

        def _once():
            cfg = load_config()
            try:
                ok = self._worker._scan_and_download(cfg)
                if ok:
                    self._set_status_threadsafe('st_idle', TEXT_DIM)
                else:
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

    def _set_progress_display_mode(self, mode: str):
        if mode == self._progress_display_mode:
            return
        try:
            self._prog_bar.stop()
            if mode == 'scan':
                self._prog_bar.configure(mode='indeterminate')
                self._prog_bar.start()
            else:
                self._prog_bar.configure(mode='determinate')
        except (tk.TclError, AttributeError):
            return
        self._progress_display_mode = mode

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
        scan = self._worker.get_scan_state()
        try:
            if prog:
                self._set_progress_display_mode('download')
                done, total, speed, title = prog
                if total > 0:
                    pct = int(done * 100 / total)
                    self._prog_bar.set(max(0.0, min(1.0, pct / 100)))
                    self._prog_pct.configure(text=f'{pct}%')
                    speed_str = (f'{speed / 1024:.0f} KB/s' if speed < 1024 * 1024
                                 else f'{speed / 1024 / 1024:.1f} MB/s')
                    self._prog_info.configure(text=f'{done}/{total} | {speed_str}')
                else:
                    # Preparing phase (0, 0, ...)
                    self._prog_bar.set(0)
                    self._prog_pct.configure(text='')
                    self._prog_info.configure(text=T('st_preparing'))
                short = title[:50] + '...' if len(title) > 50 else title
                self._prog_title.configure(text=f'↓ {short}', text_color=TEXT_PRI)
            elif scan:
                self._set_progress_display_mode('scan')
                site, category, page, eligible_count = scan
                self._prog_pct.configure(text='')
                self._prog_info.configure(
                    text=T('st_candidates_found', count=eligible_count))
                self._prog_title.configure(
                    text=T('st_scan_progress', site=site,
                           category=category, page=page),
                    text_color=ACCENT)
            else:
                self._set_progress_display_mode('idle')
                self._prog_bar.set(0)
                self._prog_pct.configure(text='')
                self._prog_info.configure(text='')
                self._prog_title.configure(text=T('st_progress_idle'), text_color=TEXT_SEC)
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
        self._worker.cancel_active_download()
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
