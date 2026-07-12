#!/usr/bin/env python
# coding: utf-8
"""Cross-site video identity and version classification for SmallTool."""

from collections import defaultdict
import re
from urllib.parse import unquote, urlsplit


DEFAULT_VERSION_PREFERENCE = 'chinese-subtitle'
VALID_VERSION_PREFERENCES = frozenset({
    'chinese-subtitle',
    'uncensored',
    'standard',
    'english-subtitle',
    'reducing-mosaic',
})

SOURCE_PRIORITY = {
    'JableTV': 0,
    'MissAV': 1,
    'SupJav': 2,
}

_TARGET_VERSION = {
    'category:chinese-subtitle': 'chinese-subtitle',
    'category:chinese-subtitles': 'chinese-subtitle',
    'feed:chinese-subtitle': 'chinese-subtitle',
    'category:english-subtitles': 'english-subtitle',
    'category:uncensored': 'uncensored',
    'feed:uncensored-leak': 'uncensored',
    'category:reducing-mosaic': 'reducing-mosaic',
    'category:censored': 'standard',
}

_VERSION_SUFFIXES = (
    '-uncensored-leak',
    '-chinese-subtitle',
    '-chinese-subtitles',
    '-english-subtitle',
    '-english-subtitles',
    '-reducing-mosaic',
    '-reduced-mosaic',
)


def site_from_url(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or '').casefold()
    except (TypeError, ValueError):
        return ''
    if host == 'jable.tv' or host.endswith('.jable.tv'):
        return 'JableTV'
    if (host.startswith('missav.') or host == 'missav123.com' or
            host.endswith('.missav123.com')):
        return 'MissAV'
    if host == 'supjav.com' or host.endswith('.supjav.com'):
        return 'SupJav'
    return ''


def url_slug(url: str) -> str:
    try:
        path = unquote(urlsplit(url).path).rstrip('/')
        return path.rsplit('/', 1)[-1].casefold()
    except (AttributeError, TypeError, ValueError):
        return ''


def _strip_version_suffixes(text: str) -> str:
    changed = True
    while changed:
        changed = False
        for suffix in _VERSION_SUFFIXES:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
                changed = True
                break
    return text


def canonical_code(text: str) -> str:
    """Extract a stable JAV code from a URL slug or listing title."""
    value = unquote(str(text or '')).casefold()
    value = _strip_version_suffixes(value.strip().rstrip('/'))

    match = re.search(
        r'(?<![a-z0-9])fc2\s*[-_ ]?\s*ppv\s*[-_ ]*(\d{4,9})(?!\d)',
        value, re.I)
    if match:
        return f'fc2-ppv-{match.group(1)}'

    match = re.search(
        r'(?<![a-z0-9])fc2\s*[-_ ]+(\d{4,9})(?!\d)', value, re.I)
    if match:
        return f'fc2-{match.group(1)}'

    match = re.search(
        r'(?<![a-z0-9])([a-z0-9]{1,15})[-_ ]+(\d{6})[-_](\d{3,4})(?!\d)',
        value, re.I)
    if match and re.search(r'[a-z]', match.group(1), re.I):
        return (f'{match.group(1)}-{match.group(2)}-{match.group(3)}'
                .casefold())

    match = re.search(r'(?<!\d)(\d{6})[-_](\d{3,4})(?!\d)', value)
    if match:
        return f'{match.group(1)}-{match.group(2)}'

    match = re.search(
        r'(?<![a-z0-9])([a-z0-9]{1,10}(?:-[a-z0-9]{1,10}){0,2})'
        r'[-_]+(\d{2,9})(?!\d)',
        value, re.I)
    if match and re.search(r'[a-z]', match.group(1), re.I):
        prefix = match.group(1).replace('_', '-').casefold()
        return f'{prefix}-{match.group(2)}'
    return ''


def video_code(video: dict) -> str:
    stored = str(video.get('_code') or video.get('code') or '').strip()
    if stored:
        return stored.casefold()

    site = video.get('_site') or video.get('site') or site_from_url(
        video.get('url', ''))
    if site in {'JableTV', 'MissAV'}:
        slug = _strip_version_suffixes(url_slug(video.get('url', '')))
        code = canonical_code(slug)
        if code:
            return code

    code = canonical_code(video.get('title', ''))
    if code:
        return code
    return ''


def video_versions(video: dict) -> set[str]:
    stored = video.get('_versions') or video.get('versions')
    if isinstance(stored, str) and stored in VALID_VERSION_PREFERENCES:
        return {stored}
    if isinstance(stored, (list, tuple, set, frozenset)):
        valid = {str(item) for item in stored
                 if str(item) in VALID_VERSION_PREFERENCES}
        if valid:
            return valid

    versions = set()
    target_version = _TARGET_VERSION.get(str(video.get('_target_id') or ''))
    if target_version:
        versions.add(target_version)

    slug = url_slug(video.get('url', ''))
    if slug.endswith('-uncensored-leak'):
        versions.add('uncensored')
    if slug.endswith(('-chinese-subtitle', '-chinese-subtitles')):
        versions.add('chinese-subtitle')
    if slug.endswith(('-english-subtitle', '-english-subtitles')):
        versions.add('english-subtitle')
    if slug.endswith(('-reducing-mosaic', '-reduced-mosaic')):
        versions.add('reducing-mosaic')

    title = str(video.get('title') or '').casefold()
    if ('chinese subtitle' in title or '中文字幕' in title or
            re.search(r'\[\s*中字\s*\]', title)):
        versions.add('chinese-subtitle')
    if 'english subtitle' in title or '英文字幕' in title:
        versions.add('english-subtitle')
    if ('reducing mosaic' in title or 'reduced mosaic' in title or
            'mosaic reduced' in title or
            '破壞版' in title or '破坏版' in title):
        versions.add('reducing-mosaic')
    if ('uncensored' in title or 'uncensored leak' in title or
            '無碼' in title or '无码' in title or
            slug.endswith('-uncensored-leak')):
        versions.add('uncensored')

    if not versions:
        versions.add('standard')
    return versions


def normalize_version_preference(value) -> str:
    pref = str(value or '').strip().casefold()
    if pref == 'uncensored-leak':
        pref = 'uncensored'
    if pref in VALID_VERSION_PREFERENCES:
        return pref
    return DEFAULT_VERSION_PREFERENCE


def dedupe_video_candidates(videos: list[dict], preference: str):
    """Deduplicate by code across categories/sites using version then source priority."""
    preference = normalize_version_preference(preference)
    url_versions = defaultdict(set)
    records = []

    for index, video in enumerate(videos):
        url = str(video.get('url') or '').strip().casefold()
        versions = video_versions(video)
        if url:
            url_versions[url].update(versions)
        records.append((index, video, url, video_code(video), versions))

    kept = []
    kept_records = []
    identity_indexes = {}
    decisions = []

    for index, video, url, code, versions in records:
        if url:
            versions = set(url_versions[url])
            if len(versions) > 1:
                versions.discard('standard')
            video['_versions'] = sorted(versions)
        if code:
            video['_code'] = code
        identity = f'code:{code}' if code else (f'url:{url}' if url else '')
        if not identity:
            kept.append(video)
            kept_records.append((index, video, url, code, versions))
            continue

        existing_index = identity_indexes.get(identity)
        if existing_index is None:
            identity_indexes[identity] = len(kept)
            kept.append(video)
            kept_records.append((index, video, url, code, versions))
            continue

        existing_record = kept_records[existing_index]
        existing_video = existing_record[1]
        existing_versions = existing_record[4]

        candidate_score = (
            0 if preference in versions else 1,
            0 if video.get('_already_seen') else 1,
            SOURCE_PRIORITY.get(video.get('_site'), 99),
            index,
        )
        existing_score = (
            0 if preference in existing_versions else 1,
            0 if existing_video.get('_already_seen') else 1,
            SOURCE_PRIORITY.get(existing_video.get('_site'), 99),
            existing_record[0],
        )
        if candidate_score < existing_score:
            kept[existing_index] = video
            kept_records[existing_index] = (
                index, video, url, code, versions)
            decisions.append((existing_video, video, code or url))
        else:
            decisions.append((video, existing_video, code or url))

    return kept, decisions
