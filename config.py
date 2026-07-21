import json
import os
import re
import threading
from urllib.parse import urlsplit


headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
}

MIRRORS = {
    'missav': ['missav.ai', 'missav.ws', 'missav123.com', 'missav.live'],
    'jable':  ['jable.tv', 'fs1.app'],
    'supjav': ['supjav.com'],
}

_cf_lock = threading.Lock()
_prefs_lock = threading.Lock()
_proxy_lock = threading.Lock()
_PROXY_UNSET = object()
_proxy_url_cache = _PROXY_UNSET
CF_OVERRIDES = {}
VALID_RESOLUTION_PREFS = {'highest', 'lowest', '1080', '720', '480', '360'}
VALID_SUBTITLE_PREFS = {'none', 'ja', 'en', 'zh', 'all'}
VALID_PROXY_SCHEMES = {
    'http', 'https', 'socks4', 'socks4a', 'socks5', 'socks5h',
}


def _cf_store_path():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'JableTV Downloader', 'cf_overrides.json')


def _ui_prefs_path():
    return os.path.join(os.path.dirname(_cf_store_path()), 'ui_prefs.json')


def queue_csv_path():
    return os.path.join(os.path.dirname(_ui_prefs_path()), 'download_queue.csv')


def _load_prefs():
    try:
        with open(_ui_prefs_path(), 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        return {'theme': raw}
    return {}


def _save_prefs(prefs):
    path = _ui_prefs_path()
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def get_theme():
    mode = _load_prefs().get('theme')
    if isinstance(mode, str):
        mode = mode.strip().lower()
        if mode in {'system', 'light', 'dark'}:
            return mode
    return 'system'


def set_theme(mode):
    mode = (mode or '').strip().lower()
    if mode not in {'system', 'light', 'dark'}:
        mode = 'system'
    try:
        with _prefs_lock:
            prefs = _load_prefs()
            prefs['theme'] = mode
            _save_prefs(prefs)
    except Exception:
        pass


def get_ui_lang():
    code = _load_prefs().get('lang')
    if isinstance(code, str):
        code = code.strip()
        if code in {'en', 'zh', 'zh-Hans', 'ja'}:
            return code
    return None


def set_ui_lang(code):
    code = (code or '').strip()
    if code not in {'en', 'zh', 'zh-Hans', 'ja'}:
        code = 'en'
    try:
        with _prefs_lock:
            prefs = _load_prefs()
            prefs['lang'] = code
            _save_prefs(prefs)
    except Exception:
        pass


def get_resolution_pref():
    pref = _load_prefs().get('resolution')
    if isinstance(pref, str):
        pref = pref.strip().lower()
        if pref in VALID_RESOLUTION_PREFS:
            return pref
    return 'highest'


def set_resolution_pref(pref):
    pref = str(pref or '').strip().lower()
    if pref not in VALID_RESOLUTION_PREFS:
        pref = 'highest'
    try:
        with _prefs_lock:
            prefs = _load_prefs()
            prefs['resolution'] = pref
            _save_prefs(prefs)
    except Exception:
        pass


def get_subtitle_pref():
    pref = _load_prefs().get('subtitle_mode')
    if isinstance(pref, str):
        pref = pref.strip().lower()
        if pref in VALID_SUBTITLE_PREFS:
            return pref
    return 'none'


def set_subtitle_pref(pref):
    pref = str(pref or '').strip().lower()
    if pref not in VALID_SUBTITLE_PREFS:
        pref = 'none'
    try:
        with _prefs_lock:
            prefs = _load_prefs()
            prefs['subtitle_mode'] = pref
            _save_prefs(prefs)
    except Exception:
        pass


def normalize_proxy_url(raw):
    """Validate one app-scoped proxy URL; bare host:port means HTTP."""
    value = str(raw or '').strip()
    if not value:
        return ''
    if re.search(r'[\x00-\x20\x7f]', value):
        raise ValueError('Proxy URL cannot contain whitespace or control characters')
    if '://' not in value:
        value = 'http://' + value
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        parsed.port  # force validation of malformed/out-of-range ports
    except (TypeError, ValueError):
        raise ValueError('Invalid proxy URL') from None
    if scheme not in VALID_PROXY_SCHEMES or not hostname:
        raise ValueError('Unsupported or incomplete proxy URL')
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Proxy URL must not contain a path, query, or fragment')
    return value


def get_proxy_url():
    global _proxy_url_cache
    if _proxy_url_cache is _PROXY_UNSET:
        with _proxy_lock:
            if _proxy_url_cache is _PROXY_UNSET:
                try:
                    value = normalize_proxy_url(_load_prefs().get('proxy_url'))
                except ValueError:
                    value = ''
                _proxy_url_cache = value
    return _proxy_url_cache


def set_proxy_url(raw):
    global _proxy_url_cache
    value = normalize_proxy_url(raw)
    with _prefs_lock:
        prefs = _load_prefs()
        if value:
            prefs['proxy_url'] = value
        else:
            prefs.pop('proxy_url', None)
        _save_prefs(prefs)
    with _proxy_lock:
        _proxy_url_cache = value
    return value


def proxy_request_kwargs():
    """Keyword arguments accepted by requests and curl_cffi requests."""
    value = get_proxy_url()
    if not value:
        return {}
    return {'proxies': {'http': value, 'https': value}}


def _parse_cf_clearance(raw):
    if raw is None:
        return ''
    s = re.sub(r'[\x00-\x1f\x7f]+', '', str(raw).strip())
    if not s:
        return ''
    if 'cf_clearance=' in s:
        m = re.search(r'cf_clearance=([^;,\s]+)', s)
        return m.group(1) if m else ''
    return s.strip('\'"')


def _norm_host(host):
    h = (host or '').strip().lower().rstrip('.')
    if ':' in h:
        h = h.split(':', 1)[0].rstrip('.')
    return h


def get_cf_override(host):
    with _cf_lock:
        entry = CF_OVERRIDES.get(_norm_host(host))
        return dict(entry) if entry else None


def cf_override_hosts():
    with _cf_lock:
        return sorted(CF_OVERRIDES.keys())


def set_cf_override(host, cookie, ua):
    global CF_OVERRIDES
    h = _norm_host(host)
    if not h:
        return
    entry = {}
    ck = _parse_cf_clearance(cookie)
    if ck:
        entry['cookie'] = ck
    ua = (ua or '').strip()
    if ua:
        entry['ua'] = ua
    with _cf_lock:
        next_overrides = dict(CF_OVERRIDES)
        if entry:
            next_overrides[h] = entry
        else:
            next_overrides.pop(h, None)
        CF_OVERRIDES = next_overrides
    save_cf_overrides()


def clear_cf_override(host):
    set_cf_override(host, '', '')


def load_cf_overrides():
    global CF_OVERRIDES
    path = _cf_store_path()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except FileNotFoundError:
        with _cf_lock:
            CF_OVERRIDES = {}
        return
    except Exception:
        try:
            os.replace(path, path + '.bak')
        except Exception:
            pass
        with _cf_lock:
            CF_OVERRIDES = {}
        return

    parsed = {}
    if isinstance(raw, dict):
        for host, entry in raw.items():
            h = _norm_host(host)
            if not h or not isinstance(entry, dict):
                continue
            clean = {}
            cookie = entry.get('cookie')
            ua = entry.get('ua')
            if isinstance(cookie, str):
                cookie = _parse_cf_clearance(cookie)
                if cookie:
                    clean['cookie'] = cookie
            if isinstance(ua, str) and ua.strip():
                clean['ua'] = ua.strip()
            if clean:
                parsed[h] = clean
    with _cf_lock:
        CF_OVERRIDES = parsed


def save_cf_overrides():
    try:
        path = _cf_store_path()
        folder = os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)
        with _cf_lock:
            snapshot = dict(CF_OVERRIDES)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        pass


try:
    load_cf_overrides()
except Exception:
    pass
