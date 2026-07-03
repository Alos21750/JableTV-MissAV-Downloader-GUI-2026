#!/usr/bin/env python
# coding: utf-8
"""Updater logic for the frozen Windows GUI app."""

import os
import re
import subprocess
import sys
import tempfile

import requests


REPO = "Alos21750/JableTV-MissAV-Downloader-GUI-2026"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def _session():
    """requests session that reuses the ONE shared SSLContext (ssl_util) so the
    updater's background HTTPS can't race a fresh SSLContext construction with the
    site scrapers — that race is the concurrent-SSLContext native crash (issue #25)."""
    s = requests.Session()
    try:
        import ssl_util
        s.mount('https://', ssl_util.SharedSSLAdapter())
    except Exception:
        pass
    return s


def parse_version(s):
    text = str(s or '').strip()
    if text.lower().startswith('v'):
        text = text[1:]
    parts = re.split(r'[.\-_\s+]+', text)
    nums = []
    for part in parts:
        if not part:
            continue
        m = re.match(r'\d+', part)
        nums.append(int(m.group(0)) if m else 0)
        if len(nums) >= 3:
            break
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


def check_latest(timeout=10):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "JableTV-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        with _session() as s:
            r = s.get(API_LATEST, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json()
        tag = str(data.get('tag_name') or '').strip()
        if not tag:
            return None
        version = tag[1:] if tag.lower().startswith('v') else tag
        assets = {}
        for asset in data.get('assets') or []:
            name = asset.get('name')
            url = asset.get('browser_download_url')
            if name and url:
                assets[str(name)] = str(url)
        return {
            "tag": tag,
            "version": version,
            "html_url": data.get('html_url') or '',
            "notes": str(data.get('body') or '')[:4000],
            "assets": assets,
        }
    except Exception:
        return None


def current_exe_name():
    if is_frozen():
        return os.path.basename(sys.executable)
    return 'JableTV_Modern.exe'


def is_frozen():
    return bool(getattr(sys, 'frozen', False))


def _remove_quiet(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def download_asset(url, dest_path, progress_cb=None, timeout=60):
    part_path = dest_path + '.part'
    _remove_quiet(part_path)
    try:
        with _session() as s, s.get(url, stream=True, timeout=timeout) as r:
            if r.status_code != 200:
                return False
            total = int(r.headers.get('content-length') or 0)
            downloaded = 0
            with open(part_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        try:
                            progress_cb(downloaded, total)
                        except Exception:
                            pass

        if os.path.getsize(part_path) <= 3_000_000:
            _remove_quiet(part_path)
            return False
        with open(part_path, 'rb') as f:
            if f.read(2) != b'MZ':
                _remove_quiet(part_path)
                return False
        os.replace(part_path, dest_path)
        return True
    except Exception:
        _remove_quiet(part_path)
        return False


def _bat_quote(path):
    return '"' + str(path).replace('"', '""').replace('%', '%%') + '"'


def apply_update_and_restart(new_exe_path):
    if not is_frozen():
        return False
    try:
        cur = sys.executable
        pid = os.getpid()
        bat = os.path.join(tempfile.gettempdir(), f'jabletv_update_{pid}.bat')
        body = f"""@echo off
setlocal
set /a n=0
:retry
move /Y {_bat_quote(new_exe_path)} {_bat_quote(cur)} >nul 2>&1
if not errorlevel 1 goto done
set /a n+=1
if %n% GEQ 120 goto giveup
ping -n 2 127.0.0.1 >nul
goto retry
:giveup
del {_bat_quote(new_exe_path)} >nul 2>&1
:done
start "" {_bat_quote(cur)}
del "%~f0" >nul 2>&1
"""
        encoding = 'mbcs' if os.name == 'nt' else 'utf-8'
        with open(bat, 'w', encoding=encoding, errors='replace') as f:
            f.write(body)
        flags = (
            getattr(subprocess, 'CREATE_NO_WINDOW', 0) |
            getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        )
        subprocess.Popen(['cmd', '/c', bat], creationflags=flags,
                         close_fds=True)
        return True
    except Exception:
        return False
