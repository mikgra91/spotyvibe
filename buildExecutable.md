# Build Windows executable (PyInstaller) — buildExecutable.md

## Goal
Build a Windows-first desktop executable for the Flask app **SpotyVibe** using **PyInstaller**.

## App behavior (target)
- Starts a local server at `http://127.0.0.1:5000`
- User interacts via a browser
- Bundles required runtime assets
- Does **not** bundle credentials (kept in `%LOCALAPPDATA%\spotyvibe\.credentials`)

## Hard constraints
- `python app.py` must still work.
- Android/Chaquopy build must still work.
- Do not change Android dependency pins.
- Do not rename/move: `app.py`, `templates/`, `static/`, `core/`, `prompts/`, `data/`.
- Spotify redirect URIs must remain:
  - Desktop: `http://127.0.0.1:5000/callback`
  - Android: `spotyvibe://callback`

Desktop-build-only files must remain isolated:
- `spotyvibe.spec`
- `spotyvibe_onefile.spec`
- `desktop_launcher.py`
- `build_assets/`
- `build-tools/build_exe.sh`

---

## Implementation checklist (marking completed work)

### Repo artifacts
- [x] Ensure desktop build dependencies exist (PyInstaller + Pillow in `requirements.txt`)
- [x] Add desktop entry point: `desktop_launcher.py` (runs Flask with `debug=False`, `use_reloader=False`)
- [x] Add Windows icon + generator:
  - [x] `build_assets/make_ico.py`
  - [x] `build_assets/spotyvibe.ico`
- [x] Add PyInstaller spec: `spotyvibe.spec`
  - [x] One-folder build
  - [x] Bundles runtime folders: `templates/`, `static/`, `prompts/`, `data/`
  - [x] Bundles `UserManual.md`
  - [x] `console=False` (release build)

### Still required (not yet verified here)
- [x] Confirm whether any runtime path helper (`resource_path`) is needed (only if packaged file loading fails)
- [x] Build the executable:
  - [x] `pyinstaller --noconfirm --clean spotyvibe.spec`
- [ ] Validate the packaged app by running:
  - [ ] `dist/spotyvibe/spotyvibe.exe`
- [ ] Smoke-test checklist:
  - [ ] Server starts once (no duplicate launch)
  - [ ] UI loads and functions
  - [ ] Templates/static/prompts/data load correctly
  - [ ] Credentials are read/written only in `%LOCALAPPDATA%\spotyvibe\.credentials`
  - [ ] Spotify OAuth works with `http://127.0.0.1:5000/callback`

---

## Build commands (Windows)

```bash
pip install -r requirements.txt
python build_assets/make_ico.py
python -m pytest tests/ -v

# One-folder build
pyinstaller --noconfirm --clean spotyvibe.spec
# or
./build-tools/build_exe.sh --package

# (Optional) one-file build
pyinstaller --noconfirm --clean spotyvibe_onefile.spec
# or
./build-tools/build_exe.sh --full
```

Expected output:
- One-folder: `dist/spotyvibe/spotyvibe.exe`
- One-file: `dist/spotyvibe_onefile.exe`

---

## Troubleshooting checklist
If the packaged build fails:
- Missing assets: ensure `spotyvibe.spec` includes `templates/`, `static/`, `prompts/`, `data/`, and `UserManual.md`.
- Double server start: verify `use_reloader=False` in `desktop_launcher.py`.
- OAuth mismatch: confirm the Spotify app redirect URI includes `http://127.0.0.1:5000/callback`.
- Path issues: only then consider adding a `resource_path` helper and using it for file reads.

---

## Optional follow-ups (after the above is stable)
- [x] Switch to `console=False` (release build)
- [x] Evaluate `--onefile` packaging
- [x] Auto-open browser on launch (desktop only)