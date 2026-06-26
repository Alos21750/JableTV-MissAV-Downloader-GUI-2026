import json
import os
import re
import threading


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
CF_OVERRIDES = {}
VALID_RESOLUTION_PREFS = {'highest', 'lowest', '1080', '720', '480', '360'}


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
