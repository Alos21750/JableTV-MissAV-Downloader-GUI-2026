import itertools

import pytest

from video_identity import (
    DEFAULT_VERSION_PREFERENCE,
    VALID_VERSION_PREFERENCES,
    canonical_code,
    dedupe_video_candidates,
    normalize_version_preference,
    site_from_url,
    video_code,
    video_versions,
)


@pytest.mark.parametrize(('raw', 'expected'), [
    ('IPZZ-905', 'ipzz-905'),
    ('[Chinese Subtitles] SNOS-223', 'snos-223'),
    ('FC2PPV 4931572', 'fc2-ppv-4931572'),
    ('FC2-PPV-1657563', 'fc2-ppv-1657563'),
    ('020121_429-paco', '020121-429'),
    ('1pondo-123456_789', '1pondo-123456-789'),
    ('HEYZO-1234 sample title', 'heyzo-1234'),
    ('random article 440577', ''),
    ('no confirmed code', ''),
])
def test_canonical_code_only_returns_confirmed_code_shapes(raw, expected):
    assert canonical_code(raw) == expected


@pytest.mark.parametrize(('video', 'expected'), [
    ({'_site': 'JableTV', 'url': 'https://jable.tv/videos/IPZZ-905/'},
     'ipzz-905'),
    ({'_site': 'MissAV',
      'url': 'https://missav.ai/cn/mimk-284-chinese-subtitle'},
     'mimk-284'),
    ({'_site': 'MissAV',
      'url': 'https://missav.ai/mimk-284-uncensored-leak'},
     'mimk-284'),
    ({'_site': 'SupJav', 'url': 'https://supjav.com/440577.html',
      'title': '[Reducing Mosaic] IPZZ-905'},
     'ipzz-905'),
    ({'_site': 'SupJav', 'url': 'https://supjav.com/440578.html',
      'title': 'FC2PPV 4931572'},
     'fc2-ppv-4931572'),
    ({'_site': 'SupJav', 'url': 'https://supjav.com/440579.html',
      'title': 'random article 440577'},
     ''),
])
def test_video_code_uses_site_specific_evidence(video, expected):
    assert video_code(video) == expected


@pytest.mark.parametrize(('url', 'expected'), [
    ('https://jable.tv/videos/ipzz-905/', 'JableTV'),
    ('https://cn.jable.tv/videos/ipzz-905/', 'JableTV'),
    ('https://missav.ai/mimk-284', 'MissAV'),
    ('https://missav.ws/mimk-284', 'MissAV'),
    ('https://supjav.com/440577.html', 'SupJav'),
    ('https://example.com/ipzz-905', ''),
])
def test_site_from_url(url, expected):
    assert site_from_url(url) == expected


@pytest.mark.parametrize(('video', 'expected'), [
    ({'_target_id': 'category:chinese-subtitle'}, {'chinese-subtitle'}),
    ({'_target_id': 'feed:chinese-subtitle'}, {'chinese-subtitle'}),
    ({'_target_id': 'category:uncensored'}, {'uncensored'}),
    ({'_target_id': 'feed:uncensored-leak'}, {'uncensored'}),
    ({'_target_id': 'category:censored'}, {'standard'}),
    ({'_target_id': 'category:english-subtitles'}, {'english-subtitle'}),
    ({'_target_id': 'category:reducing-mosaic'}, {'reducing-mosaic'}),
    ({'url': 'https://missav.ai/mimk-284-chinese-subtitle'},
     {'chinese-subtitle'}),
    ({'url': 'https://missav.ai/mimk-284-uncensored-leak'},
     {'uncensored'}),
    ({'title': '[English Subtitles] FSDSS-622'}, {'english-subtitle'}),
    ({'title': '[Reduced Mosaic] IPZZ-905'}, {'reducing-mosaic'}),
    ({'title': '[Uncensored] FC2PPV 4937463'}, {'uncensored'}),
    ({'title': 'DLDSS-507'}, {'standard'}),
])
def test_video_versions_cover_all_supported_sources(video, expected):
    assert video_versions(video) == expected


def _version_candidates():
    return [
        {'_site': 'JableTV', '_target_id': 'category:chinese-subtitle',
         'url': 'https://jable.tv/videos/ipzz-905/', 'title': 'IPZZ-905'},
        {'_site': 'MissAV', '_target_id': 'feed:uncensored-leak',
         'url': 'https://missav.ai/ipzz-905-uncensored-leak',
         'title': 'IPZZ-905'},
        {'_site': 'MissAV', '_target_id': 'feed:latest',
         'url': 'https://missav.ai/ipzz-905', 'title': 'IPZZ-905'},
        {'_site': 'SupJav', '_target_id': 'category:english-subtitles',
         'url': 'https://supjav.com/440576.html',
         'title': '[English Subtitles] IPZZ-905'},
        {'_site': 'SupJav', '_target_id': 'category:reducing-mosaic',
         'url': 'https://supjav.com/440577.html',
         'title': '[Reducing Mosaic] IPZZ-905'},
    ]


@pytest.mark.parametrize(('preference', 'expected_url'), [
    ('chinese-subtitle', 'https://jable.tv/videos/ipzz-905/'),
    ('uncensored', 'https://missav.ai/ipzz-905-uncensored-leak'),
    ('standard', 'https://missav.ai/ipzz-905'),
    ('english-subtitle', 'https://supjav.com/440576.html'),
    ('reducing-mosaic', 'https://supjav.com/440577.html'),
])
def test_preference_wins_across_sources_regardless_of_scan_order(
        preference, expected_url):
    candidates = _version_candidates()
    for order in itertools.permutations(candidates):
        kept, decisions = dedupe_video_candidates(
            [dict(video) for video in order], preference)
        assert [video['url'] for video in kept] == [expected_url]
        assert len(decisions) == len(candidates) - 1


def test_same_url_across_categories_unions_version_evidence():
    latest = {
        '_site': 'JableTV', '_target_id': 'feed:latest',
        'url': 'https://jable.tv/videos/ipzz-905/', 'title': 'IPZZ-905',
    }
    chinese = {
        '_site': 'JableTV', '_target_id': 'category:chinese-subtitle',
        'url': latest['url'], 'title': 'IPZZ-905',
    }
    standard_elsewhere = {
        '_site': 'MissAV', '_target_id': 'feed:latest',
        'url': 'https://missav.ai/ipzz-905', 'title': 'IPZZ-905',
    }

    kept, _ = dedupe_video_candidates(
        [latest, standard_elsewhere, chinese], 'chinese-subtitle')

    assert kept == [latest]
    assert latest['_versions'] == ['chinese-subtitle']
    assert chinese['_versions'] == ['chinese-subtitle']


def test_same_version_cross_site_tie_has_stable_source_order():
    candidates = [
        {'_site': 'SupJav', '_target_id': 'category:chinese-subtitles',
         'url': 'https://supjav.com/1.html', 'title': 'IPZZ-905'},
        {'_site': 'MissAV', '_target_id': 'feed:chinese-subtitle',
         'url': 'https://missav.ai/ipzz-905-chinese-subtitle',
         'title': 'IPZZ-905'},
        {'_site': 'JableTV', '_target_id': 'category:chinese-subtitle',
         'url': 'https://jable.tv/videos/ipzz-905/', 'title': 'IPZZ-905'},
    ]
    for order in itertools.permutations(candidates):
        kept, _ = dedupe_video_candidates(
            [dict(video) for video in order], 'chinese-subtitle')
        assert kept[0]['_site'] == 'JableTV'


def test_successful_preferred_download_prevents_cross_site_redownload():
    existing = {
        '_site': 'JableTV', '_target_id': 'category:chinese-subtitle',
        'url': 'https://jable.tv/videos/ipzz-905/', 'title': 'IPZZ-905',
        '_already_seen': True,
    }
    new = {
        '_site': 'MissAV', '_target_id': 'feed:chinese-subtitle',
        'url': 'https://missav.ai/ipzz-905-chinese-subtitle',
        'title': 'IPZZ-905',
    }

    kept, _ = dedupe_video_candidates(
        [existing, new], 'chinese-subtitle')

    assert kept == [existing]


def test_new_preferred_version_can_upgrade_prior_unpreferred_download():
    existing = {
        '_site': 'JableTV', '_target_id': 'feed:latest',
        'url': 'https://jable.tv/videos/ipzz-905/', 'title': 'IPZZ-905',
        '_already_seen': True,
    }
    new = {
        '_site': 'SupJav', '_target_id': 'category:reducing-mosaic',
        'url': 'https://supjav.com/440577.html', 'title': 'IPZZ-905',
    }

    kept, _ = dedupe_video_candidates([existing, new], 'reducing-mosaic')

    assert kept == [new]


def test_unconfirmed_codes_only_dedupe_by_exact_url():
    first = {'_site': 'SupJav', 'url': 'https://example.com/a',
             'title': 'unknown release'}
    same_url = {'_site': 'MissAV', 'url': 'https://example.com/a',
                'title': 'another unknown release'}
    different_url = {'_site': 'JableTV', 'url': 'https://example.com/b',
                     'title': 'unknown release'}

    kept, decisions = dedupe_video_candidates(
        [first, same_url, different_url], DEFAULT_VERSION_PREFERENCE)

    assert [video['url'] for video in kept] == [
        'https://example.com/a', 'https://example.com/b']
    assert len(decisions) == 1


@pytest.mark.parametrize('value', [None, '', 'bogus', object()])
def test_invalid_preferences_fall_back_to_chinese(value):
    assert normalize_version_preference(value) == DEFAULT_VERSION_PREFERENCE


def test_legacy_uncensored_value_is_normalized():
    assert normalize_version_preference('uncensored-leak') == 'uncensored'
    assert VALID_VERSION_PREFERENCES == {
        'chinese-subtitle', 'uncensored', 'standard',
        'english-subtitle', 'reducing-mosaic',
    }
