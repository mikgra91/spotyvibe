# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller spec for building a Windows desktop executable (one-file).

Build (one-file):
  pyinstaller --noconfirm --clean spotyvibe_onefile.spec

Notes:
- Includes runtime asset folders (templates/, static/, prompts/, data/)
- Includes help docs for the in-app Help modal:
    - documentation/help.en.md + help.de.md (served by /api/help)
    - documentation/guides/ (served by /api/help/guide/<slug>)
    - documentation/assets/guides/ (served by /docs/guides/<path>)
    - documentation/assets/screenshots/ (served by /docs/screenshots/<path>)
- Does NOT bundle credentials; those remain in %LOCALAPPDATA%/spotyvibe/
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
    (os.path.join(project_root, "frontend", "templates"), "frontend/templates"),
    (os.path.join(project_root, "frontend", "static"), "frontend/static"),
    (os.path.join(project_root, "prompts"), "prompts"),
    (os.path.join(project_root, "data"), "data"),
    (os.path.join(project_root, "documentation", "help.en.md"), "documentation"),
    (os.path.join(project_root, "documentation", "help.de.md"), "documentation"),
    (os.path.join(project_root, "documentation", "guides"), "documentation/guides"),
    (os.path.join(project_root, "documentation", "assets", "guides"), "documentation/assets/guides"),
    (os.path.join(project_root, "documentation", "assets", "screenshots"), "documentation/assets/screenshots"),
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

# One-file builds extract the whole bundle to a temp dir on every launch,
# which is a multi-second, feedback-free wait. The bootloader renders this
# splash BEFORE Python starts, so the user sees something immediately.
# desktop_launcher.py updates the status line via pyi_splash and closes it
# once the WebView UI has loaded.
splash = Splash(
    os.path.join(project_root, "build_assets", "splash.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(150, 214),
    text_size=11,
    text_color="#b3b3b3",
    text_default="Starting…",
    always_on_top=True,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
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
