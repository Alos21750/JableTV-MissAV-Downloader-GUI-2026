#!/usr/bin/env python
# coding: utf-8

import re
import html
import cloudscraper
try:
    from curl_cffi import requests as cffi_requests
    _use_cffi = True
except ImportError:
    _use_cffi = False
import threading as _threading
from urllib.parse import quote
from M3U8Sites.M3U8Crawler import *
from bs4 import BeautifulSoup


SUPREMEJAV = 'https://lk1.supremejav.com/supjav.php?c={}'
_BLOCKED_MSG = "所有鏡像都被 Cloudflare 阻擋（可能是你的網路/IP 信譽問題，請改用 VPN 或不同網路）"

_browser_scraper = None
_browser_scraper_lock = _threading.Lock()

def _make_scraper():
    """Fresh scraper: curl_cffi (Cloudflare-capable) if available, else cloudscraper."""
    if _use_cffi:
        return cffi_requests.Session(impersonate='chrome')
    return cloudscraper.create_scraper(browser=request_headers, delay=10)


def _extract_tv_link(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    for a in soup.select('a[data-link]'):
        if a.get_text(strip=True) == 'TV':
            return a.get('data-link', '')
    return None


def _extract_m3u8(body):
    body = body.replace('\\/', '/')
    m = re.search(r'urlPlay[\s=:\'"]+(?P<u>https?://[^\s\'"\\]+\.m3u8[^\s\'"\\]*)', body)
    if m:
        return m.group('u')
    m = re.search(r'https?://[^\s\'"\\]+\.m3u8[^\s\'"\\]*', body)
    return m.group(0) if m else None


def _extract_title(soup):
    h1 = soup.find('h1')
    return h1.get_text(strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else '')


def _strip_fake_header(data):
    """SupJav segments are MPEG-TS hidden behind a fake PNG header. Return the stream
    from the first valid MPEG-TS sync (0x47 on a 188-byte stride). Plain TS is returned unchanged."""
    if data[:1] == b'\x47':
        return data
    limit = min(len(data) - 188 * 4, 8000)
    i = 0
    while 0 <= i <= limit:
        j = data.find(b'\x47', i)
        if j < 0 or j > limit:
            break
        if data[j + 188] == 0x47 and data[j + 188 * 2] == 0x47 and data[j + 188 * 3] == 0x47 and data[j + 188 * 4] == 0x47:
            return data[j:]
        i = j + 1
    return data


def _parse_videos(soup):
    videos = []
    seen = set()
    for post in soup.select('div.post'):
        a = post.select_one('a[href*=".html"]')
        if not a:
            continue
        video_url = a['href']
        if video_url in seen:
            continue
        seen.add(video_url)
        title = html.unescape(a.get('title') or a.get_text(strip=True))
        img = post.find('img')
        thumbnail = (img.get('data-original') or img.get('data-src') or '') if img else ''
        if img and not thumbnail:
            src = img.get('src') or ''
            if not src.startswith('data:'):
                thumbnail = src
        videos.append({'url': video_url, 'title': title, 'thumbnail': thumbnail, 'duration': ''})
    return videos


class SiteSupJav(M3U8Crawler):
    website_pattern = r'https://supjav\.com/\d+\.html$'
    website_dirname_pattern = r'https://supjav\.com/(\d+)\.html$'

    def _transform_segment(self, data):
        return _strip_fake_header(data)

    def get_url_infos(self):
        with _make_scraper() as scraper:
            def _validate(resp):
                return 'data-link' in resp.text
            htmlfile, host, reason = fetch_with_mirrors(scraper, self._url, 'supjav', _validate, timeout=30)
            if reason == 'blocked':
                raise MirrorsBlockedError(_BLOCKED_MSG)
            if reason != 'ok':
                raise Exception(f"頁面解析失敗（版面改版或影片不存在）: {self._url}")

            soup = BeautifulSoup(htmlfile.content, 'html.parser')
            tv_link = _extract_tv_link(htmlfile.text)
            if not tv_link:
                raise Exception("此影片沒有支援的 TV 伺服器來源（其他來源 FST/ST/VOE 暫不支援）")

            tvid = tv_link[::-1]
            r2 = scraper.get(SUPREMEJAV.format(tvid), headers={'Referer':'https://supjav.com/'}, timeout=20)
            if r2.status_code in (403, 429, 503):
                raise MirrorsBlockedError(_BLOCKED_MSG)
            m3u8url = _extract_m3u8(r2.text)
            if not m3u8url:
                raise Exception("無法解析影片串流（SupJav 來源改版或暫時失效）")

        title = _extract_title(soup)
        self._targetName = html.unescape(title)
        self._imageUrl = None
        self._m3u8url = m3u8url
        self._extra_headers = {}


class SupJavBrowser:
    _url_root = 'https://supjav.com'
    _scraper = None

    CATEGORIES = [
        ('最近更新', 'https://supjav.com/'),
        ('本週熱門', 'https://supjav.com/popular?sort=week'),
        ('本月熱門', 'https://supjav.com/popular?sort=month'),
        ('無碼', 'https://supjav.com/category/uncensored-jav'),
        ('有碼', 'https://supjav.com/category/censored-jav'),
        ('素人', 'https://supjav.com/category/amateur'),
        ('中文字幕', 'https://supjav.com/category/chinese-subtitles'),
        ('英文字幕', 'https://supjav.com/category/english-subtitles'),
        ('破壞版', 'https://supjav.com/category/reducing-mosaic'),
    ]

    @classmethod
    def _get_scraper(cls):
        global _browser_scraper
        if _browser_scraper is None:
            with _browser_scraper_lock:
                if _browser_scraper is None:
                    _browser_scraper = _make_scraper()
        cls._scraper = _browser_scraper
        return _browser_scraper

    @classmethod
    def fetch_categories(cls):
        return [{'name': n, 'url': u, 'count': 0} for n, u in cls.CATEGORIES]

    @classmethod
    def fetch_page(cls, url):
        def _validate(resp):
            s = BeautifulSoup(resp.content, 'html.parser')
            return bool(s.select('div.post a[href*=".html"]'))
        resp, host, reason = fetch_with_mirrors(cls._get_scraper(), url, 'supjav', _validate)
        if reason == 'blocked':
            raise MirrorsBlockedError(url)
        if reason != 'ok':
            return []
        try:
            soup = BeautifulSoup(resp.content, 'html.parser')
            return _parse_videos(soup)
        except Exception:
            return []

    @classmethod
    def page_url(cls, base, page):
        if page <= 1:
            return base
        if '?s=' in base or '&s=' in base:
            root, _, qs = base.partition('?')
            return f"{root.rstrip('/')}/page/{page}/?{qs}"
        if '?' in base:
            return f"{base}&page={page}"
        return f"{base.rstrip('/')}/page/{page}"

    @classmethod
    def search_url(cls, query):
        return f"{cls._url_root}/?s={quote(query, safe='')}"

    @classmethod
    def search(cls, query):
        return cls.fetch_page(cls.search_url(query))
