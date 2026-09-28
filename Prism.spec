# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['prism/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('prism/assets', 'prism/assets')],
    hiddenimports=['exif', 'lxml', 'lxml.etree', 'plum', 'PyQt6.QtMultimedia', 'PyQt6.QtSvg', 'PyQt6.QtSvgWidgets'],
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
    name='Prism',
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
    icon=['prism/assets/logo.ico'],
)
