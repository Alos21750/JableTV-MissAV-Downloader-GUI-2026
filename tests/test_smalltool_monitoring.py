from datetime import datetime, timezone
from types import SimpleNamespace

import jable_smalltool
from smalltool_categories import find_target


def _exact_missav_targets():
    targets = []
    for name in ('亂倫', 'NTR'):
        target = find_target('MissAV', None, name)
        assert target is not None
        targets.append({
            'site': 'MissAV',
            'id': target['id'],
            'category': target['name'],
        })
    return targets


def test_exact_missav_monitoring_run_reports_scan_and_downloads(monkeypatch,
                                                                 tmp_path):
    monkeypatch.setattr(jable_smalltool, 'load_seen', lambda: {})
    monkeypatch.setattr(jable_smalltool, 'save_config', lambda _cfg: None)
    monkeypatch.setattr(jable_smalltool, 'PER_VIDEO_FETCH_DELAY_SEC', 0)

    logs = []
    statuses = []
    worker = jable_smalltool.SmallToolWorker(
        logs.append, lambda key, _color: statuses.append(key))
    scan_states = []
    original_set_scan_state = worker._set_scan_state

    def capture_scan_state(*args, **kwargs):
        original_set_scan_state(*args, **kwargs)
        scan_states.append(worker.get_scan_state())

    worker._set_scan_state = capture_scan_state
    fetch_calls = []

    def fake_fetch(site_name, url):
        assert site_name == 'MissAV'
        fetch_calls.append(url)
        if 'page=2' in url:
            return []
        slug = 'ntr-sample' if '/NTR' in url else 'incest-sample'
        return [{
            'url': f'https://missav.ai/{slug}-001',
            'title': slug,
        }]

    worker._fetch_page_for_site = fake_fetch
    worker._fetch_missav_video_date = lambda _url: (
        datetime(2026, 7, 11, tzinfo=timezone.utc), '2026-07-11')
    downloaded = []
    worker._download_one = lambda video, dest: downloaded.append(
        (video['url'], dest))

    cfg = {
        'output_folder': str(tmp_path),
        'baseline_date': '2026-04-11',
        'first_run_done': False,
        'selected_targets': _exact_missav_targets(),
    }

    assert worker._scan_and_download(cfg) is True
    assert len(downloaded) == 2
    assert statuses[0] == 'st_scanning'
    assert 'st_downloading' in statuses
    assert any(state and state[0] == 'MissAV' and state[2] == 1
               for state in scan_states)
    assert any(state and state[3] == 2 for state in scan_states)
    assert worker.get_scan_state() is None
    assert any('/dm57/' in url and '/genres/' in url for url in fetch_calls)
    assert any('/dm757/' in url and '/NTR' in url for url in fetch_calls)
    assert any('First run' in line and '2026-04-11' in line for line in logs)


def test_missav_same_code_uses_selected_version_regardless_of_order():
    standard = {
        '_site': 'MissAV',
        'url': 'https://missav.ai/mimk-284',
        'title': 'MIMK-284',
    }
    subtitle = {
        '_site': 'MissAV',
        'url': 'https://missav.ai/cn/mimk-284-chinese-subtitle',
        'title': 'MIMK-284',
    }
    leaked = {
        '_site': 'MissAV',
        'url': 'https://missav.ai/mimk-284-uncensored-leak',
        'title': 'MIMK-284',
    }
    unrelated = {
        '_site': 'MissAV',
        'url': 'https://missav.ai/fc2-ppv-1234567',
        'title': 'FC2-PPV-1234567',
    }

    for preference, expected in (
            ('chinese-subtitle', subtitle),
            ('uncensored-leak', leaked),
            ('standard', standard)):
        for ordered in ([standard, subtitle, leaked, unrelated],
                        [leaked, subtitle, standard, unrelated]):
            kept, decisions = jable_smalltool._dedupe_missav_candidates(
                ordered, preference)
            kept_urls = [video['url'] for video in kept]

            assert kept_urls.count(expected['url']) == 1
            assert sum('mimk-284' in url for url in kept_urls) == 1
            assert unrelated['url'] in kept_urls
            assert len(decisions) == 2
            assert all(code == 'mimk-284'
                       for _dropped, _kept, code in decisions)

    default_kept, _ = jable_smalltool._dedupe_missav_candidates(
        [standard, leaked, subtitle])
    assert default_kept == [subtitle]

    assert jable_smalltool._missav_video_code(unrelated) == 'fc2-ppv-1234567'


def test_worker_defaults_to_chinese_subtitle_for_duplicate_missav_code(
        monkeypatch, tmp_path):
    monkeypatch.setattr(jable_smalltool, 'load_seen', lambda: {})
    monkeypatch.setattr(jable_smalltool, 'save_seen', lambda _seen: None)
    monkeypatch.setattr(jable_smalltool, 'save_config', lambda _cfg: None)
    monkeypatch.setattr(jable_smalltool, 'PER_VIDEO_FETCH_DELAY_SEC', 0)

    logs = []
    worker = jable_smalltool.SmallToolWorker(logs.append)
    worker._fetch_page_for_site = lambda _site, url: ([] if 'page=2' in url else [
        {'url': 'https://missav.ai/hone-297', 'title': 'HONE-297'},
        {'url': 'https://missav.ai/hone-297-uncensored-leak', 'title': 'HONE-297'},
        {'url': 'https://missav.ai/hone-297-chinese-subtitle', 'title': 'HONE-297'},
    ])
    worker._fetch_missav_video_date = lambda _url: (
        datetime(2026, 7, 11, tzinfo=timezone.utc), '2026-07-11')
    downloaded = []
    worker._download_one = lambda video, dest: downloaded.append(
        (video['url'], dest))

    target = find_target('MissAV', None, '亂倫')
    cfg = {
        'output_folder': str(tmp_path),
        'baseline_date': '2026-04-11',
        'first_run_done': False,
        'selected_targets': [{
            'site': 'MissAV', 'id': target['id'], 'category': target['name'],
        }],
    }

    assert worker._scan_and_download(cfg) is True
    assert downloaded == [(
        'https://missav.ai/hone-297-chinese-subtitle', str(tmp_path))]
    assert worker._seen['https://missav.ai/hone-297']['skipped'] is True
    assert worker._seen[
        'https://missav.ai/hone-297-uncensored-leak']['skipped'] is True
    assert any('[DEDUP] hone-297' in line for line in logs)


def test_changed_preference_reconsiders_version_skipped_by_dedup(
        monkeypatch, tmp_path):
    subtitle_url = 'https://missav.ai/mimk-284-chinese-subtitle'
    monkeypatch.setattr(jable_smalltool, 'load_seen', lambda: {
        'https://missav.ai/mimk-284': {
            'title': 'MIMK-284', 'skipped': False,
        },
        subtitle_url: {
            'title': 'MIMK-284', 'skipped': True,
            'reason': 'duplicate-version',
        },
    })
    monkeypatch.setattr(jable_smalltool, 'save_seen', lambda _seen: None)
    monkeypatch.setattr(jable_smalltool, 'save_config', lambda _cfg: None)
    monkeypatch.setattr(jable_smalltool, 'PER_VIDEO_FETCH_DELAY_SEC', 0)

    worker = jable_smalltool.SmallToolWorker(lambda _line: None)
    worker._fetch_page_for_site = lambda _site, url: ([] if 'page=2' in url else [
        {'url': subtitle_url, 'title': 'MIMK-284'},
    ])
    worker._fetch_missav_video_date = lambda _url: (
        datetime(2026, 7, 12, tzinfo=timezone.utc), '2026-07-12')
    downloaded = []
    worker._download_one = lambda video, _dest: downloaded.append(video['url'])
    target = find_target('MissAV', None, '亂倫')
    cfg = {
        'output_folder': str(tmp_path),
        'baseline_date': '2026-04-11',
        'missav_version_preference': 'chinese-subtitle',
        'first_run_done': False,
        'selected_targets': [{
            'site': 'MissAV', 'id': target['id'], 'category': target['name'],
        }],
    }

    assert worker._scan_and_download(cfg) is True
    assert downloaded == [subtitle_url]


class _FakeWidget:
    def __init__(self):
        self.visible = True

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class _FakePackable:
    def __init__(self):
        self.packed = True
        self.pack_kwargs = None
        self.config = {}

    def pack(self, **kwargs):
        self.packed = True
        self.pack_kwargs = kwargs

    def pack_forget(self):
        self.packed = False

    def pack_configure(self, **kwargs):
        self.pack_kwargs = kwargs

    def configure(self, **kwargs):
        self.config.update(kwargs)


def test_category_filter_hides_empty_groups_instead_of_blank_space():
    app = jable_smalltool.SmallToolApp.__new__(jable_smalltool.SmallToolApp)
    ntr = _FakeWidget()
    other = _FakeWidget()
    matching_frame = _FakePackable()
    empty_frame = _FakePackable()
    app._category_filter_var = SimpleNamespace(get=lambda: 'NTR')
    app._filter_groups = [
        {'frame': empty_frame, 'items': [(other, 'incest')]},
        {'frame': matching_frame, 'items': [(ntr, 'ntr')]},
    ]

    app._filter_targets()

    assert other.visible is False
    assert empty_frame.packed is False
    assert ntr.visible is True
    assert matching_frame.packed is True


def test_monitoring_can_collapse_and_restore_category_panel():
    app = jable_smalltool.SmallToolApp.__new__(jable_smalltool.SmallToolApp)
    app._categories_collapsed = False
    app._selection_panel = _FakePackable()
    app._category_tabview = _FakePackable()
    app._category_filter_box = _FakePackable()
    app._categories_toggle_btn = _FakePackable()

    app._set_categories_collapsed(True)

    assert app._categories_collapsed is True
    assert app._category_tabview.packed is False
    assert app._category_filter_box.packed is False
    assert app._selection_panel.pack_kwargs == {'fill': 'x', 'expand': False}
    assert app._categories_toggle_btn.config['text'] == jable_smalltool.T(
        'st_categories_expand')

    app._set_categories_collapsed(False)

    assert app._categories_collapsed is False
    assert app._category_tabview.packed is True
    assert app._category_filter_box.packed is True
    assert app._selection_panel.pack_kwargs == {
        'fill': 'both', 'expand': True}
    assert app._categories_toggle_btn.config['text'] == jable_smalltool.T(
        'st_categories_collapse')
