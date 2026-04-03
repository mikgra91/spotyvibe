# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller spec for building a Windows desktop executable.

Build (one-folder):
  pyinstaller --noconfirm --clean spotyvibe.spec

Notes:
- Includes runtime asset folders (templates/, static/, prompts/, data/)
- Includes documentation/help.md for the in-app Help modal (/api/help)
- Does NOT bundle credentials; those remain in %LOCALAPPDATA%\spotyvibe\
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
    (os.path.join(project_root, "frontend", "templates"), "frontend/templates"),
    (os.path.join(project_root, "frontend", "static"), "frontend/static"),
    (os.path.join(project_root, "prompts"), "prompts"),
    (os.path.join(project_root, "data"), "data"),
    (os.path.join(project_root, "documentation", "help.md"), "documentation"),
]

a = Analysis(
    [os.path.join(project_root, "desktop_launcher.py")],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=["webview", "clr_loader", "pythonnet", "markdown.extensions.tables", "markdown.extensions.fenced_code", "markdown.extensions.toc"],
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
    name="spotyvibe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=os.path.join(project_root, "build_assets", "spotyvibe.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="spotyvibe",
)
