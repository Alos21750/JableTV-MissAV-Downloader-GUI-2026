#!/usr/bin/env python
# coding: utf-8
"""Local subtitle generation shared by the Modern and SmallTool GUIs.

Japanese speech recognition runs locally via the official whisper.cpp Windows
build. English and Traditional Chinese text are translated with Google's free,
no-key web endpoint after transcription; the video itself is never uploaded.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

import requests

import config
from M3U8Sites.M3U8Crawler import locate_ffmpeg
from ssl_util import SharedSSLAdapter


WHISPER_VERSION = 'v1.9.1'
WHISPER_ARCHIVE_URL = (
    'https://github.com/ggml-org/whisper.cpp/releases/download/'
    f'{WHISPER_VERSION}/whisper-bin-x64.zip'
)
WHISPER_ARCHIVE_SHA256 = (
    '7d8be46ecd31828e1eb7a2ecdd0d6b314feafd82163038ab6092594b0a063539'
)
WHISPER_ARCHIVE_SIZE = 7_982_101

MODEL_NAME = 'ggml-base-q5_1.bin'
MODEL_URL = f'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{MODEL_NAME}'
MODEL_SHA256 = '422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898'
MODEL_SIZE = 59_707_625

VAD_MODEL_NAME = 'ggml-silero-v6.2.0.bin'
VAD_MODEL_URL = (
    'https://huggingface.co/ggml-org/whisper-vad/resolve/main/'
    + VAD_MODEL_NAME
)
VAD_MODEL_SHA256 = '2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987'
VAD_MODEL_SIZE = 885_098

GOOGLE_TRANSLATE_URL = 'https://translate.googleapis.com/translate_a/single'
VALID_SUBTITLE_MODES = {'none', 'ja', 'en', 'zh', 'all'}

ProgressCallback = Callable[[str, Optional[int]], None]
CancelCheck = Callable[[], bool]

_runtime_lock = threading.Lock()
_generation_lock = threading.Lock()
_verified_paths: set[str] = set()


class SubtitleError(RuntimeError):
    """A user-facing subtitle generation failure."""


class SubtitleCancelled(SubtitleError):
    """Raised when the owning download job is cancelled."""


@dataclass(frozen=True)
class SubtitleResult:
    files: tuple[str, ...]
    generated: tuple[str, ...]


@dataclass(frozen=True)
class SrtCue:
    index: str
    timing: str
    text: str


def normalize_subtitle_mode(value) -> str:
    mode = str(value or '').strip().lower()
    aliases = {
        'off': 'none', 'disabled': 'none',
        'jp': 'ja', 'japanese': 'ja',
        'english': 'en',
        'zh-tw': 'zh', 'traditional-chinese': 'zh', 'chinese': 'zh',
        'multi': 'all', 'multilingual': 'all',
    }
    mode = aliases.get(mode, mode)
    return mode if mode in VALID_SUBTITLE_MODES else 'none'


def subtitle_languages(mode) -> tuple[str, ...]:
    mode = normalize_subtitle_mode(mode)
    if mode == 'all':
        return ('ja', 'en', 'zh-TW')
    if mode == 'zh':
        return ('zh-TW',)
    if mode in ('ja', 'en'):
        return (mode,)
    return ()


def subtitle_paths(video_path: str) -> dict[str, str]:
    stem = os.path.splitext(os.path.abspath(video_path))[0]
    return {
        'ja': stem + '.ja.srt',
        'en': stem + '.en.srt',
        'zh-TW': stem + '.zh-TW.srt',
    }


def parse_srt(text: str) -> list[SrtCue]:
    normalized = str(text or '').lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n[ \t]*\n', normalized.strip()) if normalized.strip() else []
    cues: list[SrtCue] = []
    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 3 or '-->' not in lines[1]:
            raise SubtitleError('Whisper produced an invalid SRT subtitle file')
        cue_text = '\n'.join(lines[2:]).strip()
        cues.append(SrtCue(lines[0].strip(), lines[1].strip(), cue_text))
    return cues


def render_srt(cues: Iterable[SrtCue]) -> str:
    parts = []
    for cue in cues:
        parts.append(f'{cue.index}\n{cue.timing}\n{cue.text.strip()}')
    return '\n\n'.join(parts) + ('\n' if parts else '')


def _cache_root() -> str:
    base = (os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
            or os.path.join(os.path.expanduser('~'), '.cache'))
    return os.path.join(base, 'JableTV Downloader', 'subtitle_tools')


def _notify(callback: Optional[ProgressCallback], stage: str,
            percent: Optional[int] = None) -> None:
    if callback:
        callback(stage, percent)


def _check_cancel(cancel_check: Optional[CancelCheck]) -> None:
    if cancel_check and cancel_check():
        raise SubtitleCancelled('Subtitle generation cancelled')


def _session() -> requests.Session:
    session = requests.Session()
    session.mount('https://', SharedSSLAdapter(pool_connections=4, pool_maxsize=4))
    session.headers.update({
        'User-Agent': config.headers.get('User-Agent', 'JableTV Downloader'),
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8,ja;q=0.7',
    })
    return session


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _is_verified(path: str, expected_size: int, expected_sha256: str) -> bool:
    key = os.path.abspath(path)
    if key in _verified_paths and os.path.isfile(path):
        return True
    try:
        if os.path.getsize(path) != expected_size:
            return False
        if _sha256(path).lower() != expected_sha256.lower():
            return False
    except OSError:
        return False
    _verified_paths.add(key)
    return True


def _download_verified(url: str, destination: str, expected_size: int,
                       expected_sha256: str, stage: str,
                       progress_callback: Optional[ProgressCallback],
                       cancel_check: Optional[CancelCheck]) -> str:
    if _is_verified(destination, expected_size, expected_sha256):
        return destination

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    part = destination + '.part'
    try:
        os.remove(part)
    except FileNotFoundError:
        pass

    session = _session()
    try:
        kwargs = config.proxy_request_kwargs()
        with session.get(url, stream=True, timeout=(20, 120), **kwargs) as response:
            response.raise_for_status()
            received = 0
            total = int(response.headers.get('Content-Length') or expected_size)
            with open(part, 'wb') as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    _check_cancel(cancel_check)
                    if not chunk:
                        continue
                    handle.write(chunk)
                    received += len(chunk)
                    pct = int(received * 100 / total) if total > 0 else None
                    _notify(progress_callback, stage, min(100, pct) if pct is not None else None)
                handle.flush()
                os.fsync(handle.fileno())
        if not _is_verified(part, expected_size, expected_sha256):
            raise SubtitleError('Downloaded subtitle component failed integrity verification')
        os.replace(part, destination)
        _verified_paths.add(os.path.abspath(destination))
        return destination
    except SubtitleCancelled:
        raise
    except SubtitleError:
        raise
    except Exception as exc:
        raise SubtitleError(f'Unable to download subtitle component: {type(exc).__name__}') from exc
    finally:
        session.close()
        try:
            os.remove(part)
        except FileNotFoundError:
            pass


def _find_whisper_exe(folder: str) -> Optional[str]:
    if not os.path.isdir(folder):
        return None
    for root, _dirs, files in os.walk(folder):
        for filename in files:
            if filename.lower() == 'whisper-cli.exe':
                return os.path.join(root, filename)
    return None


def _safe_extract_zip(archive: str, destination: str) -> None:
    root = os.path.abspath(destination)
    with zipfile.ZipFile(archive) as bundle:
        total_size = sum(info.file_size for info in bundle.infolist())
        if total_size > 300 * 1024 * 1024:
            raise SubtitleError('Subtitle component archive is unexpectedly large')
        for info in bundle.infolist():
            member = info.filename.replace('\\', '/')
            if not member or member.endswith('/'):
                continue
            target = os.path.abspath(os.path.join(root, *member.split('/')))
            if os.path.commonpath([root, target]) != root:
                raise SubtitleError('Unsafe path found in subtitle component archive')
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with bundle.open(info) as source, open(target, 'wb') as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def _prepare_runtime(progress_callback: Optional[ProgressCallback],
                     cancel_check: Optional[CancelCheck]) -> tuple[str, str, str]:
    with _runtime_lock:
        _check_cancel(cancel_check)
        root = _cache_root()
        archive = os.path.join(root, 'downloads', f'whisper-{WHISPER_VERSION}-x64.zip')
        runtime_dir = os.path.join(root, 'whisper', WHISPER_VERSION)
        marker = os.path.join(runtime_dir, '.source-sha256')
        exe = _find_whisper_exe(runtime_dir)
        marker_ok = False
        try:
            with open(marker, 'r', encoding='ascii') as handle:
                marker_ok = handle.read().strip() == WHISPER_ARCHIVE_SHA256
        except OSError:
            pass
        if not exe or not marker_ok:
            _notify(progress_callback, 'runtime', 0)
            _download_verified(
                WHISPER_ARCHIVE_URL, archive, WHISPER_ARCHIVE_SIZE,
                WHISPER_ARCHIVE_SHA256, 'runtime', progress_callback, cancel_check)
            parent = os.path.dirname(runtime_dir)
            os.makedirs(parent, exist_ok=True)
            temp_dir = tempfile.mkdtemp(prefix='whisper-install-', dir=parent)
            try:
                _safe_extract_zip(archive, temp_dir)
                if not _find_whisper_exe(temp_dir):
                    raise SubtitleError('whisper-cli.exe is missing from the official archive')
                with open(os.path.join(temp_dir, '.source-sha256'), 'w', encoding='ascii') as handle:
                    handle.write(WHISPER_ARCHIVE_SHA256)
                if os.path.isdir(runtime_dir):
                    shutil.rmtree(runtime_dir)
                os.replace(temp_dir, runtime_dir)
                temp_dir = ''
            finally:
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            exe = _find_whisper_exe(runtime_dir)
        if not exe:
            raise SubtitleError('Unable to install whisper.cpp')

        model = os.path.join(root, 'models', MODEL_NAME)
        _notify(progress_callback, 'model', 0)
        _download_verified(
            MODEL_URL, model, MODEL_SIZE, MODEL_SHA256,
            'model', progress_callback, cancel_check)
        vad_model = os.path.join(root, 'models', VAD_MODEL_NAME)
        _download_verified(
            VAD_MODEL_URL, vad_model, VAD_MODEL_SIZE, VAD_MODEL_SHA256,
            'model', progress_callback, cancel_check)
        return exe, model, vad_model


def _run_process(args: list[str], log_path: str,
                 cancel_check: Optional[CancelCheck]) -> None:
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    with open(log_path, 'wb') as log_handle:
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=log_handle,
            stderr=subprocess.STDOUT, creationflags=creationflags)
        while process.poll() is None:
            if cancel_check and cancel_check():
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                raise SubtitleCancelled('Subtitle generation cancelled')
            time.sleep(0.25)
        if process.returncode != 0:
            raise SubtitleError(f'Subtitle process exited with code {process.returncode}')


def _extract_audio(video_path: str, wav_path: str, log_path: str,
                   cancel_check: Optional[CancelCheck]) -> None:
    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise SubtitleError('FFmpeg is unavailable')
    _run_process([
        ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
        '-i', video_path, '-vn', '-ac', '1', '-ar', '16000',
        '-c:a', 'pcm_s16le', wav_path,
    ], log_path, cancel_check)


def _run_whisper(exe: str, model: str, vad_model: str, wav_path: str,
                 output_base: str, log_path: str,
                 cancel_check: Optional[CancelCheck]) -> str:
    threads = max(1, min(8, (os.cpu_count() or 4) - 1))
    args = [
        exe, '-m', model, '-f', wav_path, '-l', 'ja',
        '-osrt', '-of', output_base, '-np', '-t', str(threads),
        '-bs', '1', '-bo', '1', '-nf', '-sns',
        '--vad', '-vm', vad_model,
    ]
    _run_process(args, log_path, cancel_check)
    result = output_base + '.srt'
    if not os.path.isfile(result):
        raise SubtitleError('Whisper did not create an SRT subtitle file')
    return result


def _atomic_copy(source: str, destination: str) -> None:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temp = destination + '.tmp'
    shutil.copyfile(source, temp)
    os.replace(temp, destination)


def _translation_batches(texts: list[str], max_chars: int = 3200):
    start = 0
    current: list[str] = []
    current_size = 0
    for text in texts:
        clean = re.sub(r'\s+', ' ', text or '').strip()
        added = len(clean) + (32 if current else 0)
        if current and current_size + added > max_chars:
            yield start, current
            start += len(current)
            current = []
            current_size = 0
        current.append(clean)
        current_size += len(clean) + (32 if len(current) > 1 else 0)
    if current:
        yield start, current


def _translated_payload(session: requests.Session, payload: str,
                        target_language: str,
                        cancel_check: Optional[CancelCheck]) -> str:
    params = {'client': 'gtx', 'sl': 'ja', 'tl': target_language, 'dt': 't'}
    last_error = None
    for attempt in range(3):
        _check_cancel(cancel_check)
        try:
            response = session.post(
                GOOGLE_TRANSLATE_URL, params=params, data={'q': payload},
                timeout=(15, 90), **config.proxy_request_kwargs())
            response.raise_for_status()
            data = response.json()
            fragments = data[0] if isinstance(data, list) and data else []
            translated = ''.join(
                str(fragment[0]) for fragment in fragments
                if isinstance(fragment, list) and fragment and fragment[0] is not None)
            if translated or not payload:
                return translated
            raise ValueError('empty translation')
        except SubtitleCancelled:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                for _ in range((attempt + 1) * 4):
                    _check_cancel(cancel_check)
                    time.sleep(0.25)
    raise SubtitleError(
        f'Google free translation is temporarily unavailable: {type(last_error).__name__}')


def _translate_batch(session: requests.Session, texts: list[str],
                     target_language: str,
                     cancel_check: Optional[CancelCheck]) -> list[str]:
    if not texts:
        return []
    marker = lambda index: f'[[[JABLE_SEG_{index:06d}]]]'
    payload_parts = []
    for index, text in enumerate(texts):
        if index:
            payload_parts.append(f'\n{marker(index)}\n')
        payload_parts.append(text)
    translated = _translated_payload(
        session, ''.join(payload_parts), target_language, cancel_check)
    pieces = re.split(r'\s*\[\[\[JABLE_SEG_\d{6}\]\]\]\s*', translated)
    if len(pieces) == len(texts):
        return [piece.strip() for piece in pieces]
    # Marker preservation is normally reliable.  Fall back to one cue per
    # request instead of ever assigning a translation to the wrong timestamp.
    return [
        _translated_payload(session, text, target_language, cancel_check).strip()
        for text in texts
    ]


def translate_srt(source_path: str, destination_path: str, target_language: str,
                  progress_stage: str,
                  progress_callback: Optional[ProgressCallback] = None,
                  cancel_check: Optional[CancelCheck] = None) -> str:
    with open(source_path, 'r', encoding='utf-8-sig') as handle:
        cues = parse_srt(handle.read())
    if not cues:
        _atomic_write_text(destination_path, '')
        return destination_path

    texts = [cue.text for cue in cues]
    translated_texts: list[str] = [''] * len(texts)
    session = _session()
    try:
        for start, batch in _translation_batches(texts):
            translated = _translate_batch(
                session, batch, target_language, cancel_check)
            translated_texts[start:start + len(batch)] = translated
            pct = int((start + len(batch)) * 100 / len(texts))
            _notify(progress_callback, progress_stage, pct)
    finally:
        session.close()

    translated_cues = [
        SrtCue(cue.index, cue.timing, translated_texts[index])
        for index, cue in enumerate(cues)
    ]
    _atomic_write_text(destination_path, render_srt(translated_cues))
    return destination_path


def translate_srt_to_zh_tw(source_path: str, destination_path: str,
                           progress_callback: Optional[ProgressCallback] = None,
                           cancel_check: Optional[CancelCheck] = None) -> str:
    return translate_srt(
        source_path, destination_path, 'zh-TW', 'translate_zh',
        progress_callback, cancel_check)


def _atomic_write_text(destination: str, text: str) -> None:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temp = destination + '.tmp'
    with open(temp, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, destination)


def _existing(path: str) -> bool:
    return os.path.isfile(path)


def generate_subtitles(video_path: str, mode,
                       progress_callback: Optional[ProgressCallback] = None,
                       cancel_check: Optional[CancelCheck] = None) -> SubtitleResult:
    """Generate requested sidecar SRT files next to ``video_path``.

    Output names are ``.ja.srt``, ``.en.srt``, and ``.zh-TW.srt`` so media
    players can expose them as independently selectable subtitle tracks.
    """
    normalized = normalize_subtitle_mode(mode)
    requested = subtitle_languages(normalized)
    if not requested:
        return SubtitleResult((), ())
    video_path = os.path.abspath(video_path)
    if not os.path.isfile(video_path):
        raise SubtitleError('Downloaded video file was not found')

    paths = subtitle_paths(video_path)
    generated: list[str] = []
    with _generation_lock:
        _check_cancel(cancel_check)
        missing = [language for language in requested if not _existing(paths[language])]
        if not missing:
            return SubtitleResult(tuple(paths[language] for language in requested), ())

        _notify(progress_callback, 'queued', None)
        existing_japanese = paths['ja'] if _existing(paths['ja']) else None
        need_whisper = bool(missing and not existing_japanese)
        exe = model = vad_model = None
        if need_whisper:
            exe, model, vad_model = _prepare_runtime(
                progress_callback, cancel_check)
        with tempfile.TemporaryDirectory(prefix='jable-subtitle-') as temp_dir:
            wav = os.path.join(temp_dir, 'audio.wav')
            log = os.path.join(temp_dir, 'process.log')
            if need_whisper:
                _notify(progress_callback, 'audio', None)
                _extract_audio(video_path, wav, log, cancel_check)

            japanese_source = existing_japanese
            need_japanese_pass = bool(missing)
            if need_japanese_pass and not japanese_source:
                _notify(progress_callback, 'transcribe_ja', None)
                japanese_source = _run_whisper(
                    exe, model, vad_model, wav,
                    os.path.join(temp_dir, 'japanese'), log, cancel_check)

            if 'ja' in missing and japanese_source:
                _atomic_copy(japanese_source, paths['ja'])
                japanese_source = paths['ja']
                generated.append(paths['ja'])

            if 'en' in missing:
                _notify(progress_callback, 'translate_en', None)
                try:
                    translate_srt(
                        japanese_source, paths['en'], 'en', 'translate_en',
                        progress_callback, cancel_check)
                    generated.append(paths['en'])
                except SubtitleCancelled:
                    raise
                except Exception:
                    if not _existing(paths['ja']):
                        _atomic_copy(japanese_source, paths['ja'])
                    raise

            if 'zh-TW' in missing:
                if not japanese_source:
                    raise SubtitleError('Japanese transcription is unavailable')
                try:
                    translate_srt_to_zh_tw(
                        japanese_source, paths['zh-TW'],
                        progress_callback, cancel_check)
                    generated.append(paths['zh-TW'])
                except SubtitleCancelled:
                    raise
                except Exception:
                    # Preserve a useful, timestamped fallback even when the
                    # free network translation endpoint is temporarily down.
                    if not _existing(paths['ja']):
                        _atomic_copy(japanese_source, paths['ja'])
                    raise

        _notify(progress_callback, 'done', 100)
        return SubtitleResult(
            tuple(paths[language] for language in requested if _existing(paths[language])),
            tuple(generated),
        )
