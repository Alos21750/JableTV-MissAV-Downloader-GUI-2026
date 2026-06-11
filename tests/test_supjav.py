from urllib.parse import urljoin
import sys
import types


def _stub_runtime_dependency(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


def _cloudscraper_stub():
    mod = types.ModuleType('cloudscraper')

    def create_scraper(*args, **kwargs):
        raise AssertionError('cloudscraper should not be used by offline tests')

    mod.create_scraper = create_scraper
    return mod


def _m3u8_stub():
    mod = types.ModuleType('m3u8')
    mod.load = lambda *args, **kwargs: None
    return mod


_stub_runtime_dependency('cloudscraper', _cloudscraper_stub)
_stub_runtime_dependency('m3u8', _m3u8_stub)

import M3U8Sites.M3U8Crawler as crawler_mod
from bs4 import BeautifulSoup
from M3U8Sites.M3U8Crawler import M3U8Crawler
from M3U8Sites.SiteSupJav import (
    SiteSupJav,
    SupJavBrowser,
    _extract_m3u8,
    _extract_title,
    _extract_tv_link,
    _parse_videos,
    _strip_fake_header,
)


def test_supjav_validate_url_is_anchored():
    assert SiteSupJav.validate_url('https://supjav.com/433866.html') == '433866'
    assert SiteSupJav.validate_url('https://supjav.com/433866.html/x') is None
    assert SiteSupJav.validate_url('https://jable.tv/videos/x/') is None


def test_supjav_page_url():
    assert SupJavBrowser.page_url('https://supjav.com/category/uncensored-jav', 2) == 'https://supjav.com/category/uncensored-jav/page/2'
    assert SupJavBrowser.page_url('https://supjav.com/popular?sort=week', 2) == 'https://supjav.com/popular?sort=week&page=2'
    assert SupJavBrowser.page_url('https://supjav.com/', 2) == 'https://supjav.com/page/2'
    assert SupJavBrowser.page_url('https://supjav.com/?s=fc2', 2) == 'https://supjav.com/page/2/?s=fc2'
    base = 'https://supjav.com/category/uncensored-jav'
    assert SupJavBrowser.page_url(base, 1) == base


def test_extract_m3u8_from_urlplay():
    body = r"var urlPlay = 'https:\/\/cdn1.turboviplay.com\/data1\/abc\/abc.m3u8';"
    assert _extract_m3u8(body) == 'https://cdn1.turboviplay.com/data1/abc/abc.m3u8'


def test_extract_tv_link_selects_tv_button():
    html = '''
    <a data-link="tsf">FST</a>
    <a data-link="321cba">TV</a>
    <a data-link="ts">ST</a>
    <a data-link="eov">VOE</a>
    '''
    tv_link = _extract_tv_link(html)
    assert tv_link == '321cba'
    assert tv_link[::-1] == 'abc123'


def test_extract_title_from_h1_without_og_title():
    soup = BeautifulSoup('''
    <html>
      <head><title>FC2PPV 4916515 [Limited To 200 Copies...]</title></head>
      <body><h1>FC2PPV 4916515 [Limited To 200 Copies...]</h1></body>
    </html>
    ''', 'html.parser')
    assert _extract_title(soup) == 'FC2PPV 4916515 [Limited To 200 Copies...]'


def test_parse_videos_uses_real_thumbnail_src_and_ignores_base64_placeholder():
    soup = BeautifulSoup('''
    <div class="post">
      <a href="https://supjav.com/1.html" title="Home"></a>
      <img class="thumb" src="https://img.supjav.com/home.jpg">
    </div>
    <div class="post">
      <a href="https://supjav.com/2.html" title="Category"></a>
      <img class="thumb" data-original="https://img.supjav.com/category.jpg" src="data:image/png;base64,placeholder">
    </div>
    <div class="post">
      <a href="https://supjav.com/3.html" title="Placeholder"></a>
      <img class="thumb" src="data:image/png;base64,placeholder">
    </div>
    ''', 'html.parser')
    videos = _parse_videos(soup)
    assert videos[0]['thumbnail'] == 'https://img.supjav.com/home.jpg'
    assert videos[1]['thumbnail'] == 'https://img.supjav.com/category.jpg'
    assert videos[2]['thumbnail'] == ''


def test_strip_fake_header_removes_png_prefix_from_ts():
    wrapped = b'\x89PNG\r\n\x1a\n' + b'\x00' * 180 + (b'\x47' + b'\x11' * 187) * 6
    stripped = _strip_fake_header(wrapped)
    assert stripped[:1] == b'\x47'
    assert len(stripped) == 188 * 6


def test_strip_fake_header_leaves_plain_ts_unchanged():
    plain = b'\x47' + b'\x00' * 187 * 5
    assert _strip_fake_header(plain) == plain


def test_strip_fake_header_falls_back_when_no_valid_sync_run():
    data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 300
    assert _strip_fake_header(data) == data


def test_getm3u8_playlist_handles_absolute_and_relative_variants(monkeypatch):
    assert urljoin(
        'https://cdn1.turboviplay.com/data1/x/x.m3u8',
        'https://hls4.turbosplayer.com/file/u/master.m3u8',
    ) == 'https://hls4.turbosplayer.com/file/u/master.m3u8'

    class DummyCrawler(M3U8Crawler):
        def __init__(self):
            self._m3u8url = 'https://cdn1.turboviplay.com/data1/x/x.m3u8'
            self._extra_headers = {}

    loaded = []

    def fake_load(url, headers=None):
        loaded.append(url)
        return object()

    monkeypatch.setattr(crawler_mod.m3u8, 'load', fake_load)

    dummy = DummyCrawler()
    _, variant_base = dummy._getm3u8PlayList('https://hls4.turbosplayer.com/file/u/master.m3u8')
    assert loaded[-1] == 'https://hls4.turbosplayer.com/file/u/master.m3u8'
    assert variant_base == 'https://hls4.turbosplayer.com/file/u/'

    _, variant_base = dummy._getm3u8PlayList('variant/master.m3u8')
    assert loaded[-1] == 'https://cdn1.turboviplay.com/data1/x/variant/master.m3u8'
    assert variant_base == 'https://cdn1.turboviplay.com/data1/x/variant/'
