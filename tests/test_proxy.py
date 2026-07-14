import json

import pytest

import config
from M3U8Sites import M3U8Crawler as crawler


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('127.0.0.1:7890', 'http://127.0.0.1:7890'),
        ('http://localhost:8080', 'http://localhost:8080'),
        ('https://proxy.example:8443', 'https://proxy.example:8443'),
        ('socks4://127.0.0.1:1080', 'socks4://127.0.0.1:1080'),
        ('socks5h://user:pass@proxy.example:1080',
         'socks5h://user:pass@proxy.example:1080'),
        ('', ''),
    ],
)
def test_normalize_proxy_url(raw, expected):
    assert config.normalize_proxy_url(raw) == expected


@pytest.mark.parametrize(
    'raw',
    [
        'ftp://proxy.example:21',
        'http://',
        'proxy.example:not-a-port',
        'proxy.example:70000',
        'http://proxy.example/path',
        'http://proxy.example?query=1',
        'http://proxy example:8080',
    ],
)
def test_normalize_proxy_url_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        config.normalize_proxy_url(raw)


def test_proxy_preference_round_trip_preserves_other_preferences(tmp_path, monkeypatch):
    path = tmp_path / 'ui_prefs.json'
    monkeypatch.setattr(config, '_ui_prefs_path', lambda: str(path))
    monkeypatch.setattr(config, '_proxy_url_cache', config._PROXY_UNSET)

    config.set_theme('dark')
    config.set_ui_lang('zh-Hans')
    saved = config.set_proxy_url('127.0.0.1:7890')

    assert saved == 'http://127.0.0.1:7890'
    assert config.get_proxy_url() == saved
    assert config.proxy_request_kwargs() == {
        'proxies': {'http': saved, 'https': saved},
    }
    raw = json.loads(path.read_text(encoding='utf-8'))
    assert raw['theme'] == 'dark'
    assert raw['lang'] == 'zh-Hans'

    config.set_proxy_url('')

    assert config.get_proxy_url() == ''
    assert config.proxy_request_kwargs() == {}
    raw = json.loads(path.read_text(encoding='utf-8'))
    assert 'proxy_url' not in raw
    assert raw['theme'] == 'dark'
    assert raw['lang'] == 'zh-Hans'


def test_proxy_preference_is_cached_between_requests(monkeypatch):
    calls = []
    monkeypatch.setattr(config, '_proxy_url_cache', config._PROXY_UNSET)
    monkeypatch.setattr(
        config, '_load_prefs',
        lambda: calls.append(True) or {'proxy_url': '127.0.0.1:7890'})

    assert config.get_proxy_url() == 'http://127.0.0.1:7890'
    assert config.get_proxy_url() == 'http://127.0.0.1:7890'
    assert calls == [True]


class _FakeResponse:
    status_code = 200
    headers = {}
    content = b'ok'
    text = 'ok'

    def __init__(self, url='https://example.test/video'):
        self.url = url


class _RecordingSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResponse(url)


def test_page_fetch_passes_proxy_to_scraper(monkeypatch):
    session = _RecordingSession()
    proxy = {'http': 'http://127.0.0.1:7890',
             'https': 'http://127.0.0.1:7890'}
    monkeypatch.setattr(config, 'MIRRORS', {'test': ['example.test']})
    monkeypatch.setattr(config, 'get_cf_override', lambda _host: None)
    monkeypatch.setattr(config, 'proxy_request_kwargs',
                        lambda: {'proxies': dict(proxy)})

    response, host, reason = crawler.fetch_with_mirrors(
        session, 'https://example.test/video', 'test', lambda _response: True)

    assert response.status_code == 200
    assert host == 'example.test'
    assert reason == 'ok'
    assert session.calls[0][1]['proxies'] == proxy


def test_media_fetch_passes_proxy_to_curl_cffi(monkeypatch):
    session = _RecordingSession()
    proxy = {'http': 'socks5h://127.0.0.1:1080',
             'https': 'socks5h://127.0.0.1:1080'}
    monkeypatch.setattr(crawler, '_use_cffi', True)
    monkeypatch.setattr(crawler, '_get_cffi_session', lambda: session)
    monkeypatch.setattr(config, 'proxy_request_kwargs',
                        lambda: {'proxies': dict(proxy)})

    crawler._http_get('https://cdn.example/video.m3u8',
                      {'User-Agent': 'ignored-by-cffi', 'Referer': 'https://example.test'})

    assert session.calls[0][1]['proxies'] == proxy
    assert session.calls[0][1]['headers'] == {'Referer': 'https://example.test'}
