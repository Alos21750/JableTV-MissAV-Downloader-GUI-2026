# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = []
binaries = []
hiddenimports = [
    'cloudscraper', 'Crypto.Cipher.AES', 'm3u8',
    # NiceGUI and its web stack
    'nicegui', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops',
    'uvicorn.loops.auto', 'uvicorn.protocols',
    'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on',
    'fastapi', 'starlette', 'httptools', 'websockets',
    'engineio', 'socketio', 'aiofiles', 'aiohttp',
    'python_multipart', 'jinja2', 'markdown2',
    'itsdangerous', 'anyio', 'httpx', 'httpcore',
    'h11', 'wsproto', 'bidict',
]

# Collect nicegui's static web assets (Quasar, Vue, etc.)
for pkg in ['nicegui', 'cloudscraper', 'certifi']:
    tmp = collect_all(pkg)
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# Collect submodules that PyInstaller misses
for pkg in ['uvicorn', 'fastapi', 'starlette', 'engineio', 'socketio']:
    hiddenimports += collect_submodules(pkg)


a = Analysis(
    ['..\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='JableTV_Modern',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
