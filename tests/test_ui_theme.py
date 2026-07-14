import re
import types
from pathlib import Path

import gui_modern
import jable_smalltool
import locales
import ui_theme


def _rgb(hex_color):
    return tuple(int(hex_color[index:index + 2], 16) / 255
                 for index in (1, 3, 5))


def _luminance(hex_color):
    channels = []
    for value in _rgb(hex_color):
        channels.append(value / 12.92 if value <= 0.04045
                        else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(a, b):
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_responsive_breakpoints_prioritize_readability():
    assert ui_theme.browse_columns_for_width(979) == 2
    assert ui_theme.browse_columns_for_width(1080) == 3
    assert ui_theme.browse_columns_for_width(1499) == 3
    assert ui_theme.browse_columns_for_width(1500) == 4
    assert ui_theme.category_columns_for_width(1119) == 2
    assert ui_theme.category_columns_for_width(1120) == 3


def test_shared_palette_is_valid_and_used_by_both_apps():
    tokens = (
        ui_theme.ACCENT, ui_theme.BG_DARK, ui_theme.BG_CARD,
        ui_theme.TEXT_PRI, ui_theme.TEXT_SEC, ui_theme.BORDER,
    )
    assert all(len(token) == 2 for token in tokens)
    assert all(re.fullmatch(r'#[0-9A-Fa-f]{6}', color)
               for token in tokens for color in token)
    assert gui_modern.ACCENT is ui_theme.ACCENT
    assert jable_smalltool.ACCENT is ui_theme.ACCENT


def test_primary_text_contrast_is_accessible_in_both_themes():
    for index in (0, 1):
        assert _contrast(ui_theme.TEXT_PRI[index], ui_theme.BG_DARK[index]) >= 7
        assert _contrast(ui_theme.TEXT_PRI[index], ui_theme.BG_CARD[index]) >= 7


def test_current_version_and_global_smalltool_copy_are_complete():
    assert gui_modern.APP_VERSION == jable_smalltool.APP_VERSION == '2.5.29'
    required = {
        'st_activity', 'st_progress_idle', 'st_footer_short',
        'st_categories_expand', 'st_categories_collapse',
        'st_scanning', 'st_downloading', 'st_scan_progress',
        'st_candidates_found',
        'st_calendar', 'st_date_quick', 'st_date_month_1',
        'st_date_month_2', 'st_folder_error',
        'st_version_preference', 'st_pref_chinese',
        'st_pref_uncensored', 'st_pref_standard',
        'st_pref_english', 'st_pref_reducing_mosaic',
    }
    for language, strings in locales.STRINGS.items():
        assert strings['version_label'] == 'v2.5.29', language
        assert required <= strings.keys(), language


def test_windows_version_resources_match_app_version():
    root = Path(__file__).resolve().parents[1]
    generator = (root / 'build_tmp' / 'gen_version.py').read_text(
        encoding='utf-8')
    assert 'VERSION = (2, 5, 29, 0)' in generator
    for name in ('JableTV_Modern.version', 'Jable_smalltool.version'):
        resource = (root / 'build_tmp' / name).read_text(encoding='utf-8')
        assert 'filevers=(2, 5, 29, 0)' in resource
        assert "StringStruct('FileVersion', '2.5.29.0')" in resource


def test_global_version_selector_saves_internal_preference(monkeypatch):
    app = jable_smalltool.SmallToolApp.__new__(jable_smalltool.SmallToolApp)
    app._cfg = {}
    saved = []
    monkeypatch.setattr(jable_smalltool, 'save_config',
                        lambda cfg: saved.append(dict(cfg)))

    app._on_version_change(jable_smalltool.T('st_pref_uncensored'))

    assert app._cfg['version_preference'] == 'uncensored'
    assert saved[-1]['version_preference'] == 'uncensored'


def test_smalltool_selected_count_reflects_target_vars_only():
    app = jable_smalltool.SmallToolApp.__new__(jable_smalltool.SmallToolApp)
    captured = {}
    app._selected_count_lbl = types.SimpleNamespace(
        configure=lambda **kwargs: captured.update(kwargs))
    app._check_vars = {
        'JableTV|__group__|feeds': types.SimpleNamespace(get=lambda: True),
        'JableTV|feed:latest': types.SimpleNamespace(get=lambda: True),
        'MissAV|feed:latest': types.SimpleNamespace(get=lambda: False),
    }

    app._update_selected_count()

    assert captured['text'].startswith('1 ')
    assert captured['text_color'] is ui_theme.ACCENT
