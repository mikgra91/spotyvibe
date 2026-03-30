# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller spec for building a Windows desktop executable (one-file).

Build (one-file):
  pyinstaller --noconfirm --clean spotyvibe_onefile.spec

Notes:
- Includes runtime asset folders (templates/, static/, prompts/, data/)
- Includes UserManual.md for the in-app Help modal (/api/help)
- Does NOT bundle credentials; those remain in %LOCALAPPDATA%\spotyvibe\
- One-file builds have a slower cold start because PyInstaller extracts
  bundled files to a temporary directory on launch.
"""

from __future__ import annotations

import os

block_cipher = None

spec_dir = globals().get("SPECPATH")
if spec_dir:
    project_root = os.path.abspath(spec_dir)
else:
    # Fallback for running the spec as a normal Python file.
    project_root = os.path.abspath(os.path.dirname(__file__))

# Bundle folders the Flask app loads at runtime.
# Note: Spec `datas` entries are (src, dest) tuples. When `src` is a
# directory, PyInstaller copies it recursively.
datas = [
    (os.path.join(project_root, "templates"), "templates"),
    (os.path.join(project_root, "static"), "static"),
    (os.path.join(project_root, "prompts"), "prompts"),
    (os.path.join(project_root, "data"), "data"),
    (os.path.join(project_root, "UserManual.md"), "."),
]

a = Analysis(
    [os.path.join(project_root, "desktop_launcher.py")],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="spotyvibe_onefile",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=os.path.join(project_root, "build_assets", "spotyvibe.ico"),
)
