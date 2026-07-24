import json
import zipfile

import pytest

from scripts import build_local_translation_pack as pack


def _model_inputs(tmp_path):
    converted = tmp_path / 'converted'
    for spec in pack.MODELS:
        model = converted / spec.directory
        model.mkdir(parents=True)
        for filename in spec.runtime_files:
            (model / filename).write_bytes(
                f'{spec.key}:{filename}'.encode('utf-8'))
        (model / 'README.md').write_text(
            f'# {spec.repository}\n', encoding='utf-8')
    apache = tmp_path / 'Apache-2.0.txt'
    apache.write_text('Apache test license\n', encoding='utf-8')
    fugu = tmp_path / 'FuguMT-NOTICE.txt'
    fugu.write_text('Fugu test notice\n', encoding='utf-8')
    return converted, apache, fugu


def test_model_pack_build_is_byte_reproducible_and_contract_verified(tmp_path):
    converted, apache, fugu = _model_inputs(tmp_path)
    first = tmp_path / 'first.zip'
    second = tmp_path / 'second.zip'

    first_result = pack.build_archive(converted, first, apache, fugu)
    second_result = pack.build_archive(converted, second, apache, fugu)

    assert first.read_bytes() == second.read_bytes()
    assert first_result['sha256'] == second_result['sha256']
    assert first_result['size'] == second_result['size']
    pack.verify_archive(first)

    with zipfile.ZipFile(first) as archive:
        manifest = json.loads(archive.read('manifest.json'))
    assert manifest['schema_version'] == 2
    assert manifest['provenance']['conversion_environment'] == {
        'architecture': '64-bit',
        'implementation': 'CPython',
        'machine': 'AMD64',
        'python': '3.12.10',
    }
    assert set(manifest['models']) == {'ja-en', 'en-zh'}
    assert (
        'models/fugumt-ja-en-int8/vocab.json'
        in manifest['models']['ja-en']['runtime_files']
    )


def test_model_pack_verifier_rejects_schema_or_zip_metadata_tampering(tmp_path):
    converted, apache, fugu = _model_inputs(tmp_path)
    original = tmp_path / 'original.zip'
    pack.build_archive(converted, original, apache, fugu)

    with zipfile.ZipFile(original) as archive:
        payload = {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
        }

    manifest = json.loads(payload['manifest.json'])
    manifest['schema_version'] = 1
    payload['manifest.json'] = pack._canonical_json(manifest)
    bad_schema = tmp_path / 'bad-schema.zip'
    with zipfile.ZipFile(bad_schema, 'w') as archive:
        for name in sorted(payload):
            archive.writestr(pack._zip_info(name), payload[name])
    with pytest.raises(pack.PackBuildError, match='schema'):
        pack.verify_archive(bad_schema)

    manifest['schema_version'] = 2
    payload['manifest.json'] = pack._canonical_json(manifest)
    bad_metadata = tmp_path / 'bad-metadata.zip'
    with zipfile.ZipFile(bad_metadata, 'w') as archive:
        for index, name in enumerate(sorted(payload)):
            info = pack._zip_info(name)
            if index == 0:
                info.external_attr = 0o100600 << 16
            archive.writestr(info, payload[name])
    with pytest.raises(pack.PackBuildError, match='metadata'):
        pack.verify_archive(bad_metadata)


@pytest.mark.parametrize(
    'path',
    ('', '/absolute', r'C:\drive', '../escape', 'a/../b', 'a//b', r'a\b'),
)
def test_model_pack_verifier_rejects_unsafe_member_paths(path):
    with pytest.raises(pack.PackBuildError, match='Unsafe'):
        pack._validate_archive_path(path)


def test_conversion_lock_file_matches_checked_toolchain():
    lock_path = (
        pack._default_repo_root()
        / 'scripts'
        / 'local_translation_conversion_requirements.txt'
    )
    locked = {}
    for line in lock_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, version = line.split('==', 1)
        locked[name] = version

    assert locked == pack.PINNED_CONVERSION_PACKAGES
    assert pack.CONVERSION_PYTHON_VERSION == '3.12.10'
    assert pack.CONVERSION_MACHINE == 'AMD64'
