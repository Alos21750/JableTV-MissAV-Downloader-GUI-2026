#!/usr/bin/env python
# coding: utf-8

import platform
import os
import re
import threading
import requests
import urllib.request
import m3u8
from Crypto.Cipher import AES
from config import headers
import concurrent.futures
import copy
import time

request_headers = {'browser': 'firefox', 'platform': platform.system().lower()}
default_max_workers = min(os.cpu_count() * 2, 16) if os.cpu_count() else 8

_session_lock = threading.Lock()
_session = None

# ── Global speed limiter (token bucket) ──────────────────────────
class _SpeedLimiter:
    """Thread-safe token-bucket rate limiter shared across all downloads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._limit_bps = 0  # 0 = unlimited
        self._tokens = 0.0
        self._last = time.time()

    def set_limit(self, mbps: float) -> None:
        with self._lock:
            self._limit_bps = int(mbps * 1024 * 1024) if mbps > 0 else 0
            self._tokens = float(self._limit_bps)
            self._last = time.time()

    def acquire(self, nbytes: int) -> None:
        with self._lock:
            limit = self._limit_bps
        if limit <= 0:
            return
        while nbytes > 0:
            with self._lock:
                now = time.time()
                self._tokens += (now - self._last) * self._limit_bps
                self._last = now
                if self._tokens > self._limit_bps:
                    self._tokens = float(self._limit_bps)
                take = min(nbytes, int(self._tokens))
                if take > 0:
                    self._tokens -= take
                    nbytes -= take
            if nbytes > 0:
                time.sleep(0.05)

speed_limiter = _SpeedLimiter()


def _get_session():
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = requests.Session()
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=32,
                    pool_maxsize=64,
                    max_retries=2,
                )
                _session.mount('http://', adapter)
                _session.mount('https://', adapter)
    return _session


class M3U8Crawler:
    """A base class for all m3u8 crawl website tools."""
    skip_pattern = False

    @classmethod
    def validate_url(cls, url):
        if not url or url == '': return None
        result = re.match(cls.website_dirname_pattern, url, flags=re.I)
        if result: return result.group(1)
        return None

    def __init__(self, url, savepath="", silence=False):
        self.silence = silence
        self._tsList = []
        self._key_content = None   # raw bytes of AES key
        self._key_method = None    # e.g. 'AES-128'
        self._key_iv = None        # hex IV string (may be None)
        self._downloadList = []
        self._t_executor = None
        self._t_future = None
        self._t2_executor = None
        self._cancel_job = None
        self._extra_headers = {}   # subclass may set (e.g. Referer)
        self._dirName = None
        self._dest_folder = None
        self._temp_folder = None
        self._targetName = None
        self._imageUrl = None
        self._m3u8url = None
        self._max_workers = default_max_workers
        self._progress_callback = None   # (downloaded, total, speed_bps) -> None
        self._speed_lock = threading.Lock()
        self._bytes_downloaded = 0
        self._speed_start = 0.0
        try:
            self._dirName = self.validate_url(url)
            if not self._dirName: return
            self._url = url
            if (savepath is None) or (savepath == ''):
                self._dest_folder = os.path.join(os.getcwd(), self._dirName)
            else:
                self._dest_folder = os.path.abspath(savepath)
            self._temp_folder = os.path.join(self._dest_folder, self._dirName)

            self.get_url_infos()
            if self.is_url_vaildate():
                if self._targetName:
                    self._targetName = re.sub(r'[^\w\-_\. ]', '', self._targetName)
                if not self.silence:
                    if self._targetName: print("檔案名稱: " + self._targetName, flush=True)
                    if self._dest_folder: print("儲存位置: " + self._dest_folder, flush=True)
                    if self._imageUrl: print("縮圖: " + self._imageUrl, flush=True)

        except Exception as exc:
            self._targetName = self._imageUrl = self._m3u8url = None
            print(f"下載網址 {url} 錯誤!! ({exc})", flush=True)

    def get_url_infos(self): raise Exception("Must implement get_url_infos()")
    def target_name(self): return self._targetName
    def dest_folder(self): return self._dest_folder
    def is_url_vaildate(self): return True if self._m3u8url else False

    def _create_temp_folder(self):
        if not os.path.exists(self._temp_folder):
            os.makedirs(self._temp_folder, exist_ok=True)

    def _create_dest_folder(self):
        if not os.path.exists(self._dest_folder):
            os.makedirs(self._dest_folder, exist_ok=True)

    def _get_video_savename(self):
        return os.path.join(self._dest_folder, self._targetName + ".mp4")

    def _get_image_savename(self):
        if self._imageUrl is None: return None
        return os.path.join(self._dest_folder, self._targetName + ".jpg")

    def get_url_full(self): return self._url

    def is_target_video_exist(self):
        return os.path.exists(self._get_video_savename())

    def is_target_image_exist(self):
        if self._imageUrl is None: return True
        return os.path.exists(self._get_image_savename())

    def _m3u8_headers(self):
        """Merged headers for m3u8 and segment requests."""
        return {**headers, **self._extra_headers}

    def _getm3u8PlayList(self, uri):
        m3u8urlPath = self._m3u8url.split('/')
        if uri.startswith('/'): m3u8urlPath = m3u8urlPath[:3]
        else: m3u8urlPath.pop(-1)
        baseurl = '/'.join(m3u8urlPath)
        playListUrl = baseurl + '/' + uri.lstrip('/')
        m3u8obj = m3u8.load(playListUrl, headers=self._m3u8_headers())
        # Segments are relative to the variant playlist, not the master
        variantBase = playListUrl.rsplit('/', 1)[0] + '/'
        return m3u8obj, variantBase

    def _create_m3u8(self):
        m3u8urlList = self._m3u8url.split('/')
        m3u8urlList.pop(-1)
        downloadurl = '/'.join(m3u8urlList) + '/'

        m3u8obj = m3u8.load(self._m3u8url, headers=self._m3u8_headers())
        if len(m3u8obj.playlists) > 0:
            # Pick highest quality variant
            best = max(m3u8obj.playlists,
                       key=lambda p: p.stream_info.bandwidth if p.stream_info else 0)
            m3u8obj, downloadurl = self._getm3u8PlayList(best.uri)

        # Extract key info (store bytes + IV, not a cipher - cipher is NOT thread-safe)
        self._key_content = None
        self._key_method = None
        self._key_iv = None
        for key in m3u8obj.keys:
            if key and key.uri:
                m3u8_key_uri = key.uri
                if not m3u8_key_uri.startswith('http'):
                    m3u8_key_uri = downloadurl + m3u8_key_uri
                resp = _get_session().get(m3u8_key_uri, headers=self._m3u8_headers(), timeout=15)
                self._key_content = resp.content
                self._key_method = getattr(key, 'method', 'AES-128')
                self._key_iv = getattr(key, 'iv', None)
                break  # use first key

        # Build segment URL list
        self._tsList = []
        for seg in m3u8obj.segments:
            uri = seg.uri
            if uri.startswith('https://') or uri.startswith('http://'):
                tsUrl = uri
            else:
                tsUrl = downloadurl + uri
            self._tsList.append(tsUrl)

    def _make_cipher(self, seq_num=0):
        """Create a fresh AES cipher for one segment (thread-safe)."""
        if not self._key_content:
            return None
        if self._key_iv:
            iv_hex = self._key_iv.replace("0x", "").replace("0X", "")
            iv_bytes = bytes.fromhex(iv_hex.zfill(32))
        else:
            # Default: segment sequence number as 16-byte big-endian IV
            iv_bytes = seq_num.to_bytes(16, 'big')
        return AES.new(self._key_content, AES.MODE_CBC, iv_bytes)

    def _deleteMp4Chunks(self):
        for url in self._tsList:
            fileName = url.split('/')[-1].rsplit('.', 1)[0]
            saveName = os.path.join(self._temp_folder, fileName + ".mp4")
            if os.path.exists(saveName):
                try: os.remove(saveName)
                except OSError: pass

    def _mergeMp4Chunks(self):
        start_time = time.time()
        saveName = self._get_video_savename()
        number_of_chunk = len(self._tsList)
        print(f'開始合成影片...共有 {number_of_chunk} 個片段', flush=True)
        # Remove stale output file
        if os.path.exists(saveName):
            os.remove(saveName)
        for i, ts_url in enumerate(self._tsList):
            file = ts_url.split('/')[-1].rsplit('.', 1)[0] + '.mp4'
            full_path = os.path.join(self._temp_folder, file)
            if os.path.exists(full_path) and not self._cancel_job:
                with open(full_path, 'rb') as f1:
                    with open(saveName, 'ab') as f2:
                        f2.write(f1.read())
                number_of_chunk -= 1
                print(f'\r合成影片中, 剩餘 {number_of_chunk} 個片段', end="")
            else:
                if os.path.exists(saveName):
                    os.remove(saveName)
                if not self._cancel_job:
                    print(f"\n{file} 片段遺失, 合成失敗!!!", flush=True)
                return 0
        spent_time = time.time() - start_time
        print(f'\n合成完成，花費 {spent_time:.1f} 秒', flush=True)
        self._deleteMp4Chunks()
        if self._temp_folder != self._dest_folder:
            try: os.removedirs(self._temp_folder)
            except OSError: pass
        return spent_time

    def _scrape(self, task):
        """Download and decrypt one segment. task=(seq_num, url)"""
        seq_num, url = task
        fileName = url.split('/')[-1].rsplit('.', 1)[0]
        saveName = os.path.join(self._temp_folder, fileName + ".mp4")
        if os.path.exists(saveName):
            # Segment already on disk (e.g. from a resumed job) — drop from pending
            with self._speed_lock:
                self._pending_set.discard((seq_num, url))
            return True

        try:
            session = _get_session()
            response = session.get(url, headers=self._m3u8_headers(), timeout=20)
            if response.status_code != 200:
                return False
            content_ts = response.content
            speed_limiter.acquire(len(content_ts))
            if self._key_content:
                cipher = self._make_cipher(seq_num)
                content_ts = cipher.decrypt(content_ts)
            with open(saveName, 'wb') as f:
                f.write(content_ts)
            with self._speed_lock:
                self._pending_set.discard((seq_num, url))
                self._bytes_downloaded += len(content_ts)
                remain = len(self._pending_set)
                elapsed = time.time() - self._speed_start
                speed = self._bytes_downloaded / elapsed if elapsed > 0 else 0
                done = self._job_total - remain
                remain_time = (remain * elapsed / done) if done > 0 else 0
                if remain_time > 60:
                    rem_str = f"{remain_time//60:.0f}分 {remain_time%60:.0f}秒"
                else:
                    rem_str = f"{remain_time:.0f}秒"
                speed_str = f"{speed/1024:.0f} KB/s" if speed < 1024*1024 else f"{speed/1024/1024:.1f} MB/s"
                print(f'\r下載中: {done}/{self._job_total} 片段 | {speed_str} | 剩餘 {rem_str}  ', end='', flush=True)
                if self._progress_callback:
                    self._progress_callback(done, self._job_total, speed)
            return True
        except Exception:
            return False

    def _startCrawl(self):
        self._speed_start = time.time()
        self._bytes_downloaded = 0
        total = len(self._tsList)
        self._job_total = len(self._pending_set)
        print(f'共 {total} 片段，已完成 {total - self._job_total}，剩餘 {self._job_total}...', flush=True)

        max_rounds = 5
        for round_num in range(1, max_rounds + 1):
            if not self._pending_set or self._cancel_job:
                break
            tasks = list(self._pending_set)
            with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                self._t2_executor = executor
                list(executor.map(self._scrape, tasks, timeout=None))
            self._t2_executor = None
            still_pending = len(self._pending_set)
            if still_pending == 0:
                break
            if round_num < max_rounds:
                print(f'\n重試第 {round_num} 次，剩餘 {still_pending} 片段...', flush=True)

        self._t2_executor = None
        spent = time.time() - self._speed_start
        if not self._cancel_job:
            final_pending = len(self._pending_set)
            if final_pending == 0:
                print(f'\n爬取完成！花費 {spent/60:.1f} 分鐘', flush=True)
            else:
                print(f'\n爬取結束，{final_pending} 個片段失敗', flush=True)

    def _prepareCrawl(self):
        self._pending_set = set()
        for i, url in enumerate(self._tsList):
            fileName = url.split('/')[-1].rsplit('.', 1)[0]
            saveName = os.path.join(self._temp_folder, fileName + ".mp4")
            if not os.path.exists(saveName):
                self._pending_set.add((i, url))
        if self._pending_set:
            self._startCrawl()

    def download_image(self):
        if not self.is_target_image_exist():
            self._create_dest_folder()
            try:
                response = _get_session().get(self._imageUrl, headers=headers, timeout=15)
                if response.status_code != 200:
                    return None
                with open(self._get_image_savename(), 'wb') as fs:
                    fs.write(response.content)
            except Exception:
                return None
        return self._get_image_savename()

    def start_download(self):
        self._cancel_job = False
        self._create_dest_folder()
        self.download_image()
        if not self.is_target_video_exist():
            self._create_temp_folder()
            self._create_m3u8()
            if not self._cancel_job:
                self._prepareCrawl()
            if not self._cancel_job and not self._pending_set:
                self._mergeMp4Chunks()
        else:
            print("檔案已存在!!", flush=True)

    def cancel_download(self):
        print("\n取消下載....", flush=True)
        self._cancel_job = True
        if self._t2_executor:
            try: self._t2_executor.shutdown(wait=False, cancel_futures=True)
            except TypeError: self._t2_executor.shutdown(wait=False)
            self._t2_executor = None
        if self._t_executor:
            try: self._t_executor.shutdown(wait=False, cancel_futures=True)
            except TypeError: self._t_executor.shutdown(wait=False)
            self._t_executor = None
        print("\n下載已取消", flush=True)

    def begin_concurrent_download(self):
        self._t_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._t_future = self._t_executor.submit(self.start_download)

    def is_concurrent_dowload_completed(self):
        if not self._t_future or not self._t_future.done():
            return False
        self._t_future = None
        return True

    def end_concurrent_download(self):
        if self._t_executor:
            self._t_executor.shutdown(wait=False)
            self._t_executor = None


class SiteUrlList_M3U8:
    def getLinks(self): return self.links
    def getLinkDescs(self): return self.linkDescriptions
    def getListType(self): return self.listType
    def getTotalLinks(self): return self.totalLinks
    def getTotalPages(self): return self.totalPages
    def getCurrentPage(self): return self.currentPage
    def getSortType(self): return self.sortType
    def isVaildLinks(self): return False if self.islist is None else True
