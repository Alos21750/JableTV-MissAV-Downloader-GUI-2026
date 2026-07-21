import os
import zipfile

import pytest

import subtitle_engine as subtitles


def _sample_srt(text='こんにちは'):
    return f'1\n00:00:00,000 --> 00:00:01,500\n{text}\n'


def test_normalize_modes_and_language_outputs():
    assert subtitles.normalize_subtitle_mode('zh-TW') == 'zh'
    assert subtitles.normalize_subtitle_mode('multilingual') == 'all'
    assert subtitles.normalize_subtitle_mode('unknown') == 'none'
    assert subtitles.subtitle_languages('all') == ('ja', 'en', 'zh-TW')
    assert subtitles.subtitle_languages('none') == ()


def test_parse_and_render_srt_round_trip():
    source = (
        '\ufeff1\r\n00:00:00,000 --> 00:00:01,500\r\nこんにちは\r\n\r\n'
        '2\r\n00:00:02,000 --> 00:00:03,000\r\nまたね\r\n'
    )
    cues = subtitles.parse_srt(source)
    assert [cue.text for cue in cues] == ['こんにちは', 'またね']
    rendered = subtitles.render_srt(cues)
    assert '00:00:02,000 --> 00:00:03,000' in rendered
    assert rendered.endswith('\n')


def test_parse_srt_rejects_malformed_content():
    with pytest.raises(subtitles.SubtitleError):
        subtitles.parse_srt('not an srt file')


def test_translation_batches_keep_order_and_limits():
    texts = ['a' * 20, 'b' * 20, 'c' * 20]
    batches = list(subtitles._translation_batches(texts, max_chars=55))
    assert batches == [(0, ['a' * 20]), (1, ['b' * 20]), (2, ['c' * 20])]


def test_translate_srt_preserves_timestamps(monkeypatch, tmp_path):
    source = tmp_path / 'video.ja.srt'
    destination = tmp_path / 'video.zh-TW.srt'
    source.write_text(
        _sample_srt('一番目') + '\n2\n00:00:02,000 --> 00:00:03,000\n二番目\n',
        encoding='utf-8')

    class FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(subtitles, '_session', lambda: FakeSession())
    monkeypatch.setattr(
        subtitles, '_translate_batch',
        lambda _session, texts, _target, _cancel: [f'中:{text}' for text in texts])

    subtitles.translate_srt_to_zh_tw(str(source), str(destination))
    result = destination.read_text(encoding='utf-8')
    assert '00:00:00,000 --> 00:00:01,500' in result
    assert '00:00:02,000 --> 00:00:03,000' in result
    assert '中:一番目' in result
    assert '中:二番目' in result


def test_generate_all_creates_three_selectable_sidecars(monkeypatch, tmp_path):
    video = tmp_path / 'movie.mp4'
    video.write_bytes(b'video')
    stages = []

    monkeypatch.setattr(
        subtitles, '_prepare_runtime',
        lambda _cb, _cancel: ('whisper.exe', 'model.bin', 'vad.bin'))

    def fake_extract(_video, wav, _log, _cancel):
        open(wav, 'wb').close()

    def fake_whisper(_exe, _model, _vad, _wav, output_base, _log, _cancel):
        output = output_base + '.srt'
        with open(output, 'w', encoding='utf-8') as handle:
            handle.write(_sample_srt('こんにちは'))
        return output

    def fake_translate(source, destination, target, stage,
                       progress_callback=None, cancel_check=None):
        assert 'こんにちは' in open(source, encoding='utf-8').read()
        with open(destination, 'w', encoding='utf-8') as handle:
            handle.write(_sample_srt('hello' if target == 'en' else '你好'))
        if progress_callback:
            progress_callback(stage, 100)
        return destination

    monkeypatch.setattr(subtitles, '_extract_audio', fake_extract)
    monkeypatch.setattr(subtitles, '_run_whisper', fake_whisper)
    monkeypatch.setattr(subtitles, 'translate_srt', fake_translate)
    monkeypatch.setattr(
        subtitles, 'translate_srt_to_zh_tw',
        lambda source, destination, progress_callback=None, cancel_check=None:
            fake_translate(source, destination, 'zh-TW', 'translate_zh',
                           progress_callback, cancel_check))

    result = subtitles.generate_subtitles(
        str(video), 'all', progress_callback=lambda stage, pct: stages.append((stage, pct)))

    assert [os.path.basename(path) for path in result.files] == [
        'movie.ja.srt', 'movie.en.srt', 'movie.zh-TW.srt']
    assert all(os.path.isfile(path) for path in result.files)
    assert ('transcribe_ja', None) in stages
    assert ('translate_en', None) in stages
    assert ('translate_zh', 100) in stages
    assert stages[-1] == ('done', 100)


def test_chinese_failure_preserves_japanese_fallback(monkeypatch, tmp_path):
    video = tmp_path / 'movie.mp4'
    video.write_bytes(b'video')
    monkeypatch.setattr(
        subtitles, '_prepare_runtime',
        lambda _cb, _cancel: ('whisper.exe', 'model.bin', 'vad.bin'))
    monkeypatch.setattr(subtitles, '_extract_audio', lambda _v, wav, _l, _c: open(wav, 'wb').close())

    def fake_whisper(_exe, _model, _vad, _wav, output_base, _log, _cancel):
        output = output_base + '.srt'
        with open(output, 'w', encoding='utf-8') as handle:
            handle.write(_sample_srt())
        return output

    monkeypatch.setattr(subtitles, '_run_whisper', fake_whisper)
    monkeypatch.setattr(
        subtitles, 'translate_srt_to_zh_tw',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subtitles.SubtitleError('translation unavailable')))

    with pytest.raises(subtitles.SubtitleError):
        subtitles.generate_subtitles(str(video), 'zh')
    assert (tmp_path / 'movie.ja.srt').is_file()
    assert not (tmp_path / 'movie.zh-TW.srt').exists()


def test_existing_outputs_skip_runtime(monkeypatch, tmp_path):
    video = tmp_path / 'movie.mp4'
    video.write_bytes(b'video')
    for language in ('ja', 'en', 'zh-TW'):
        (tmp_path / f'movie.{language}.srt').write_text(_sample_srt(), encoding='utf-8')
    monkeypatch.setattr(
        subtitles, '_prepare_runtime',
        lambda *_args: pytest.fail('runtime must not be prepared'))
    result = subtitles.generate_subtitles(str(video), 'all')
    assert len(result.files) == 3
    assert result.generated == ()


def test_safe_zip_extraction_rejects_parent_traversal(tmp_path):
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('../outside.exe', b'bad')
    with pytest.raises(subtitles.SubtitleError):
        subtitles._safe_extract_zip(str(archive), str(tmp_path / 'extract'))
