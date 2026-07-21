import os

import gui_modern
import jable_smalltool
from subtitle_engine import SubtitleResult


class FakeDownloadJob:
    def __init__(self, video_path):
        self.video_path = str(video_path)
        self._cancel_job = False
        self._progress_callback = None

    def is_url_vaildate(self):
        return True

    def target_name(self):
        return 'sample'

    def start_download(self):
        if self._progress_callback:
            self._progress_callback(10, 10, 1000)
        return True

    def _get_video_savename(self):
        return self.video_path

    def cancel_download(self, cleanup=True):
        self._cancel_job = True


def test_modern_manager_runs_selected_subtitle_mode(monkeypatch, tmp_path):
    video = tmp_path / 'sample.mp4'
    video.write_bytes(b'video')
    job = FakeDownloadJob(video)
    monkeypatch.setattr(gui_modern.M3U8Sites, 'CreateSite', lambda _url, _dest: job)
    calls = []

    def fake_generate(path, mode, progress_callback=None, cancel_check=None):
        calls.append((path, mode))
        progress_callback('transcribe_ja', None)
        return SubtitleResult((str(tmp_path / 'sample.ja.srt'),), ())

    monkeypatch.setattr(gui_modern, 'generate_subtitles', fake_generate)
    manager = gui_modern.DownloadManager(subtitle_mode_getter=lambda: 'ja')
    manager.add_item('https://jable.tv/videos/sample/', state='等待中')

    manager._run('https://jable.tv/videos/sample/', str(tmp_path), epoch=0)

    item = manager.get_items()[0]
    assert calls == [(str(video), 'ja')]
    assert item.state == '已下載'
    assert item.progress == 100
    assert item.error == ''


def test_modern_keeps_video_and_surfaces_subtitle_failure(monkeypatch, tmp_path):
    video = tmp_path / 'sample.mp4'
    video.write_bytes(b'video')
    monkeypatch.setattr(
        gui_modern.M3U8Sites, 'CreateSite',
        lambda _url, _dest: FakeDownloadJob(video))
    monkeypatch.setattr(
        gui_modern, 'generate_subtitles',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('offline')))
    manager = gui_modern.DownloadManager(subtitle_mode_getter=lambda: 'zh')
    manager.add_item('https://jable.tv/videos/sample/', state='等待中')

    manager._run('https://jable.tv/videos/sample/', str(tmp_path), epoch=0)

    item = manager.get_items()[0]
    assert item.state == '已下載'
    assert 'offline' in item.error
    assert os.path.isfile(video)


def test_smalltool_runs_subtitles_before_marking_seen(monkeypatch, tmp_path):
    video_path = tmp_path / 'sample.mp4'
    video_path.write_bytes(b'video')
    job = FakeDownloadJob(video_path)
    monkeypatch.setattr(jable_smalltool, 'load_seen', lambda: {})
    monkeypatch.setattr(
        jable_smalltool.M3U8Sites, 'CreateSite', lambda _url, _dest: job)
    calls = []

    def fake_generate(path, mode, progress_callback=None, cancel_check=None):
        calls.append((path, mode))
        progress_callback('translate_zh', 100)
        return SubtitleResult((str(tmp_path / 'sample.zh-TW.srt'),), ())

    monkeypatch.setattr(jable_smalltool, 'generate_subtitles', fake_generate)
    worker = jable_smalltool.SmallToolWorker(lambda _line: None)
    worker._subtitle_mode = 'zh'
    marked = []
    worker._mark_seen = lambda url, title, **kwargs: marked.append((url, title))
    sample = {
        'url': 'https://missav.ai/sample', 'title': 'sample', '_site': 'MissAV'}

    result = worker._download_one(sample, str(tmp_path))

    assert result is None
    assert calls == [(str(video_path), 'zh')]
    assert marked == [('https://missav.ai/sample', 'sample')]
    assert worker.get_progress() is None


def test_smalltool_retries_when_subtitle_generation_fails(monkeypatch, tmp_path):
    video_path = tmp_path / 'sample.mp4'
    video_path.write_bytes(b'video')
    monkeypatch.setattr(jable_smalltool, 'load_seen', lambda: {})
    monkeypatch.setattr(
        jable_smalltool.M3U8Sites, 'CreateSite',
        lambda _url, _dest: FakeDownloadJob(video_path))
    monkeypatch.setattr(
        jable_smalltool, 'generate_subtitles',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('offline')))
    worker = jable_smalltool.SmallToolWorker(lambda _line: None)
    worker._subtitle_mode = 'all'
    marked = []
    worker._mark_seen = lambda *args, **kwargs: marked.append(args)

    result = worker._download_one(
        {'url': 'https://missav.ai/sample', 'title': 'sample', '_site': 'MissAV'},
        str(tmp_path))

    assert result == 'subtitle_failed'
    assert marked == []
    assert os.path.isfile(video_path)
