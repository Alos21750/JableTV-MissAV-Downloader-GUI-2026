#!/usr/bin/env python
# coding: utf-8

import re
import cloudscraper
from M3U8Sites.M3U8Crawler import *
from bs4 import BeautifulSoup


def _unpack_js_eval(script_text):
    """Decode Dean Edwards p,a,c,k,e,d packer."""
    match = re.search(
        r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(.*?)',\s*(\d+),\s*(\d+),\s*'([^']*)'\s*\.split\('\|'\)",
        script_text, re.DOTALL
    )
    if not match:
        return None
    packed, a, c, keys_str = match.group(1), int(match.group(2)), int(match.group(3)), match.group(4).split('|')

    def to_base(n, base):
        digits = '0123456789abcdefghijklmnopqrstuvwxyz'
        if n == 0: return '0'
        s = ''
        while n:
            s = digits[n % base] + s
            n //= base
        return s

    lookup = {to_base(i, a): (keys_str[i] if i < len(keys_str) and keys_str[i] else to_base(i, a))
              for i in range(c)}
    return re.sub(r'\b(\w+)\b', lambda m: lookup.get(m.group(0), m.group(0)), packed)


class SiteMissAV(M3U8Crawler):
    """Downloader for missav.ai"""
    # Matches video pages ONLY (no dm\d+ routing prefix — those are category pages):
    #   https://missav.ai/cn/sone-543-chinese-subtitle
    #   https://missav.ai/sone-543
    # Does NOT match:
    #   https://missav.ai/dm265/cn/chinese-subtitle  (category listing)
    website_pattern = r'https://(?:www\.)?missav\.(?:ai|ws)/(?:dm\d+/)?(?:cn|en|ja|ko|ms|th)/([a-zA-Z0-9][a-zA-Z0-9\-]+)|https://(?:www\.)?missav\.(?:ai|ws)/([a-z]{2,5}-\d+[a-zA-Z0-9\-]*)'
    website_dirname_pattern = r'https://(?:www\.)?missav\.(?:ai|ws)/(?:dm\d+/)?(?:(?:cn|en|ja|ko|ms|th)/)?([a-z]{2,5}-\d+[a-zA-Z0-9\-]*)'

    _shared_scraper = None
    _scraper_lock = __import__('threading').Lock()

    @classmethod
    def _get_scraper(cls):
        with cls._scraper_lock:
            if cls._shared_scraper is None:
                cls._shared_scraper = cloudscraper.create_scraper(
                    browser=request_headers, delay=10)
            return cls._shared_scraper

    def get_url_infos(self):
        import time
        scraper = self._get_scraper()
        last_exc = None
        for attempt in range(3):
            try:
                htmlfile = scraper.get(self._url, timeout=60)
                break
            except Exception as e:
                last_exc = e
                print(f'[MissAV] 嘗試 {attempt+1}/3 失敗: {e}', flush=True)
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        else:
            raise last_exc
        if htmlfile.status_code != 200:
            raise Exception(f"HTTP {htmlfile.status_code} for {self._url}")

        # Title from og:title
        og_title = re.search(r'og:title"\s+content="([^"]+)"', htmlfile.text)
        if og_title:
            self._targetName = og_title.group(1)
        else:
            soup = BeautifulSoup(htmlfile.content, 'html.parser')
            meta = soup.find('meta', property='og:title')
            self._targetName = meta.get('content', '') if meta else ''

        # Thumbnail from og:image
        og_image = re.search(r'og:image"\s+content="([^"]+)"', htmlfile.text)
        if og_image:
            self._imageUrl = og_image.group(1)

        # Extract m3u8 from packed eval blocks
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', htmlfile.text, re.DOTALL)
        for script in scripts:
            if 'eval(function' not in script or 'm3u8' not in script:
                continue
            unpacked = _unpack_js_eval(script)
            if unpacked:
                # Unpacked text has escaped quotes: source=\'https://...\'
                # Match "source=" (not source842= etc.) followed by the URL
                main_match = re.search(
                    r"source\s*=\s*[\\']*(https?://[^'\\;\s]+\.m3u8)", unpacked)
                if main_match:
                    self._m3u8url = main_match.group(1)
                    return
                # Fallback: any m3u8 URL in the block
                any_match = re.search(r'(https?://[^\'\\;\s]+\.m3u8)', unpacked)
                if any_match:
                    self._m3u8url = any_match.group(1)
                    return

        raise Exception(f"Could not find m3u8 URL for {self._url}")


class MissAVBrowser:
    """Fetches categories and video listings from missav.ai for the browse GUI."""
    _url_root = 'https://missav.ai/dm265/cn'
    _scraper = None

    # Fixed category list (from nav)
    CATEGORIES = [
        ('今日熱門', 'https://missav.ai/dm291/cn/today-hot'),
        ('本週熱門', 'https://missav.ai/dm169/cn/weekly-hot'),
        ('本月熱門', 'https://missav.ai/dm263/cn/monthly-hot'),
        ('中文字幕', 'https://missav.ai/dm265/cn/chinese-subtitle'),
        ('最近更新', 'https://missav.ai/dm515/cn/new'),
        ('新作上市', 'https://missav.ai/dm590/cn/release'),
        ('無碼流出', 'https://missav.ai/dm628/cn/uncensored-leak'),
        ('SIRO', 'https://missav.ai/dm23/cn/siro'),
        ('FC2', 'https://missav.ai/dm150/cn/fc2'),
        ('麻豆傳媒', 'https://missav.ai/dm35/cn/madou'),
        ('東京熱', 'https://missav.ai/dm29/cn/tokyohot'),
        ('一本道', 'https://missav.ai/dm2469695/cn/1pondo'),
    ]

    @classmethod
    def _get_scraper(cls):
        if cls._scraper is None:
            cls._scraper = cloudscraper.create_scraper(browser=request_headers, delay=10)
        return cls._scraper

    @classmethod
    def fetch_categories(cls):
        return [{'name': name, 'url': url, 'count': 0} for name, url in cls.CATEGORIES]

    @classmethod
    def fetch_page(cls, url):
        """Return list of dicts with url, title, thumbnail, duration."""
        try:
            r = cls._get_scraper().get(url, timeout=30)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.content, 'html.parser')
            cards = soup.select('div.thumbnail')
            videos = []
            for card in cards:
                link = card.select_one('a[href*="missav"]')
                if not link:
                    continue
                video_url = link.get('href', '')
                # Normalize: ensure it's a video page URL
                if not re.search(r'/[a-z]{2}/[a-z]', video_url):
                    continue

                img = card.select_one('img')
                thumbnail = img.get('data-src', '') if img else ''
                title_text = img.get('alt', '') if img else ''

                # Try the text link inside div.my-2
                title_a = card.select_one('div.my-2 a, div.truncate a')
                if title_a:
                    title_text = title_a.get_text(strip=True) or title_text

                duration_span = card.select_one('span.absolute.bottom-1.right-1')
                duration = duration_span.get_text(strip=True) if duration_span else ''

                if video_url:
                    videos.append({
                        'url': video_url,
                        'title': title_text,
                        'thumbnail': thumbnail,
                        'duration': duration,
                    })
            return videos
        except Exception:
            return []

    @classmethod
    def search(cls, query):
        """Search for videos matching query."""
        url = f'https://missav.ai/dm265/cn/search?query={query}'
        return cls.fetch_page(url)

    @classmethod
    def page_url(cls, base_url, page):
        """Build paginated URL."""
        if page <= 1:
            return base_url
        sep = '&' if '?' in base_url else '?'
        return f'{base_url}{sep}page={page}'
