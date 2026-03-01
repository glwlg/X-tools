# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('logo.png', '.'), ('src/ui/check.svg', 'src/ui'), ('src/plugins', 'src/plugins')]
binaries = [('Everything64.dll', '.')]
hiddenimports = ['src.ui.hosts_window', 'src.ui.screenshot_overlay', 'src.ui.pinned_image_window', 'src.plugins.hosts_tool', 'src.plugins.qr_tool', 'src.plugins.hash_tool', 'src.plugins.json_tool', 'src.plugins.url_tool', 'src.plugins.uuid_tool', 'qrcode', 'cv2', 'rapidocr_onnxruntime']
tmp_ret = collect_all('rapidocr_onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
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
    [],
    exclude_binaries=True,
    name='x-tools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['W:\\glwlg\\app\\x-tools\\logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='x-tools',
)
