"""Desktop-only entry point for PyInstaller builds.

Why this exists:
- Keeps app.py unchanged (source + Android flows stay stable)
- Forces debug=False and use_reloader=False in packaged desktop builds
- Embeds a native window (via pywebview) that renders the Flask app,
  giving users a real desktop-app experience
- Closing the window terminates the Flask server and the process cleanly —
  no orphaned background processes

The Flask app itself lives in app.py as `app`.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import socket
import sys
import threading
import time
from pathlib import Path

from app import app

# Windows DWM attribute constants (dwmapi.h)
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36
_DWMWCP_ROUND = 2  # rounded window corners (Win 11+)

# Windows ShowWindow constants
_SW_MAXIMIZE = 3
_SW_RESTORE = 9

# Win32 WM_NCHITTEST hit-test constants for resize edges
_WM_NCHITTEST = 0x0084
_HTLEFT = 10; _HTRIGHT = 11; _HTTOP = 12; _HTTOPLEFT = 13
_HTTOPRIGHT = 14; _HTBOTTOM = 15; _HTBOTTOMLEFT = 16; _HTBOTTOMRIGHT = 17
_HTCAPTION = 2
_GWL_WNDPROC = -4
_RESIZE_BORDER = 6  # px from edge that triggers resize cursor

# Title bar height (px) — roughly double the native Windows title bar.
_TITLEBAR_H = 64


def _colorref(hex_rgb: int) -> int:
    """Convert 0xRRGGBB → COLORREF 0x00BBGGRR."""
    r = (hex_rgb >> 16) & 0xFF
    g = (hex_rgb >> 8) & 0xFF
    b = hex_rgb & 0xFF
    return (b << 16) | (g << 8) | r


def _get_work_area() -> tuple[int, int, int, int]:
    """Return (x, y, width, height) of the monitor work area (excludes taskbar)."""
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def _find_hwnd() -> int | None:
    """Return the HWND of the SpotyVibe window, or None."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    return user32.FindWindowW(None, "SpotyVibe") or None


def _apply_dark_chrome() -> None:
    """Apply a Spotify-style dark border and rounded corners via DWM.

    Uses the same near-black tones as the app's CSS (--bg-main: #050608).
    Silently ignored on platforms other than Windows or older Windows builds
    that lack the DWM attributes.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = _find_hwnd()
        if not hwnd:
            return

        dwmapi = ctypes.windll.dwmapi

        def _set_attr(attr: int, value: int, unsigned: bool = False) -> None:
            ctype = ctypes.c_uint if unsigned else ctypes.c_int
            val = ctype(value)
            dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), ctypes.c_uint(attr),
                ctypes.byref(val), ctypes.sizeof(val),
            )

        _set_attr(_DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
        _set_attr(_DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND)
        _set_attr(_DWMWA_BORDER_COLOR, _colorref(0x000000), unsigned=True)
    except Exception:
        pass


def _get_storage_path() -> str:
    """Return a persistent directory for WebView2 profile data (cookies, cache).

    Uses the same base as the app's credential storage so cookies (including
    Spotify session cookies) survive across restarts and temp-folder cleanups.
    """
    base = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "spotyvibe"
    storage = base / "webview_data"
    storage.mkdir(parents=True, exist_ok=True)
    return str(storage)


# ---------------------------------------------------------------------------
# JS injected into the main window to create the custom title bar, side
# frames, and desktop-specific overrides.  Only runs when the page is
# loaded inside the pywebview wrapper.
# ---------------------------------------------------------------------------
_CHROME_JS = r"""(function() {
    if (document.getElementById('desktop-titlebar')) return;

    /* ---- CSS ---------------------------------------------------------- */
    var s = document.createElement('style');
    s.textContent = [
        'body { -webkit-app-region: no-drag; }',
        '#desktop-titlebar {',
        '  height: 64px; background: #050608;',
        '  display: flex; align-items: center; justify-content: space-between;',
        '  padding: 0 0 0 16px;',
        '  position: fixed; top: 0; left: 0; right: 0;',
        '  z-index: 999999; user-select: none; -webkit-user-select: none;',
        '  -webkit-app-region: drag;',
        '}',
        '.dt-controls { -webkit-app-region: no-drag; }',
        '.dt-title {',
        '  font-family: "Segoe UI", sans-serif; font-size: 14px;',
        '  font-weight: 700; color: #1DB954; letter-spacing: .5px;',
        '  pointer-events: none;',
        '}',
        '.dt-controls {',
        '  display: flex; align-items: stretch; height: 100%;',
        '}',
        '.dt-btn {',
        '  width: 48px; display: flex; align-items: center;',
        '  justify-content: center; background: transparent; border: none;',
        '  color: #b3b3b3; cursor: pointer; padding: 0;',
        '  transition: background .15s, color .15s;',
        '}',
        '.dt-btn:hover { background: rgba(255,255,255,.08); color: #fff; }',
        '.dt-btn:active { background: rgba(255,255,255,.12); }',
        '.dt-btn.dt-close:hover { background: #e74c3c; color: #fff; }',
        '.dt-btn.dt-close:active { background: #c0392b; }',
        '.dt-btn svg { display: block; }',
        '.desktop-frame {',
        '  position: fixed; top: 0; bottom: 0; width: 2px;',
        '  background: #000; z-index: 999999; pointer-events: none;',
        '}',
        '.desktop-frame-l { left: 0; }',
        '.desktop-frame-r { right: 0; }',
    ].join('\n');
    document.head.appendChild(s);

    /* ---- SVG icons ---------------------------------------------------- */
    var minSvg  = '<svg width="12" height="12" viewBox="0 0 12 12">'
                + '<line x1="1" y1="6" x2="11" y2="6" stroke="currentColor" stroke-width="1"/></svg>';
    var maxSvg  = '<svg width="12" height="12" viewBox="0 0 12 12">'
                + '<rect x="1.5" y="1.5" width="9" height="9" rx=".5" stroke="currentColor" stroke-width="1" fill="none"/></svg>';
    var restSvg = '<svg width="12" height="12" viewBox="0 0 12 12">'
                + '<rect x="1" y="3" width="8" height="8" rx=".5" stroke="currentColor" stroke-width="1" fill="none"/>'
                + '<polyline points="3,3 3,1 11,1 11,9 9,9" stroke="currentColor" stroke-width="1" fill="none"/></svg>';
    var closeSvg= '<svg width="12" height="12" viewBox="0 0 12 12">'
                + '<line x1="2" y1="2" x2="10" y2="10" stroke="currentColor" stroke-width="1"/>'
                + '<line x1="10" y1="2" x2="2" y2="10" stroke="currentColor" stroke-width="1"/></svg>';

    /* ---- Title bar ---------------------------------------------------- */
    var bar = document.createElement('div');
    bar.id = 'desktop-titlebar';
    bar.className = 'pywebview-drag-region';
    bar.innerHTML = '<span class="dt-title">SpotyVibe</span>'
        + '<div class="dt-controls">'
        + '<button class="dt-btn dt-minimize" aria-label="Minimize">' + minSvg + '</button>'
        + '<button class="dt-btn dt-maximize" id="dt-max-btn" aria-label="Maximize">' + maxSvg + '</button>'
        + '<button class="dt-btn dt-close" aria-label="Close">' + closeSvg + '</button>'
        + '</div>';
    document.body.prepend(bar);

    /* ---- Side frames -------------------------------------------------- */
    var fl = document.createElement('div');
    fl.className = 'desktop-frame desktop-frame-l';
    document.body.appendChild(fl);
    var fr = document.createElement('div');
    fr.className = 'desktop-frame desktop-frame-r';
    document.body.appendChild(fr);

    /* ---- Push page content below title bar ---------------------------- */
    document.documentElement.style.setProperty('--titlebar-h', '64px');
    document.body.style.paddingTop = '64px';

    /* ---- Button handlers ---------------------------------------------- */
    var maxBtn = document.getElementById('dt-max-btn');

    function updateMaxIcon(isMax) {
        maxBtn.innerHTML = isMax ? restSvg : maxSvg;
        maxBtn.setAttribute('aria-label', isMax ? 'Restore' : 'Maximize');
    }

    bar.querySelector('.dt-minimize').addEventListener('click', function() {
        pywebview.api.minimize_window();
    });
    maxBtn.addEventListener('click', async function() {
        updateMaxIcon(await pywebview.api.toggle_maximize());
    });
    bar.querySelector('.dt-close').addEventListener('click', function() {
        pywebview.api.close_window();
    });

    /* Double-click title bar → toggle maximize (standard Windows UX) */
    bar.addEventListener('dblclick', function(e) {
        if (!e.target.closest('.dt-btn')) {
            pywebview.api.toggle_maximize().then(updateMaxIcon);
        }
    });

    /* Keep icon in sync after snap-maximize / snap-restore */
    var rTimer;
    window.addEventListener('resize', function() {
        clearTimeout(rTimer);
        rTimer = setTimeout(function() {
            pywebview.api.is_maximized().then(updateMaxIcon);
        }, 120);
    });
})();"""


if sys.platform == "win32":
    # LRESULT = LONG_PTR, WPARAM = UINT_PTR, LPARAM = LONG_PTR — all
    # pointer-sized on x64.  Using 32-bit types truncates values and
    # causes access violations when forwarding messages via CallWindowProcW.
    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint,
        ctypes.c_size_t, ctypes.c_ssize_t,
    )
else:
    WNDPROC = None


def _install_resize_hook(hwnd: int) -> None:
    """Subclass the window proc to add resize-edge hit-testing on frameless windows."""
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32

    # Set correct 64-bit types — ctypes defaults to c_int which truncates
    # 64-bit pointers on x64 Windows, causing access violations.
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
        ctypes.c_size_t, ctypes.c_ssize_t,
    ]

    old_proc = user32.GetWindowLongPtrW(hwnd, _GWL_WNDPROC)

    @WNDPROC
    def new_proc(h, msg, wp, lp):
        if msg == _WM_NCHITTEST:
            # Unpack cursor position from lParam (signed 16-bit halves)
            x = ctypes.c_short(lp & 0xFFFF).value
            y = ctypes.c_short((lp >> 16) & 0xFFFF).value
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(rect))
            cx = x - rect.left
            cy = y - rect.top
            w = rect.right - rect.left
            h2 = rect.bottom - rect.top
            b = _RESIZE_BORDER

            if cy < b:
                if cx < b:
                    return _HTTOPLEFT
                if cx > w - b:
                    return _HTTOPRIGHT
                return _HTTOP
            if cy > h2 - b:
                if cx < b:
                    return _HTBOTTOMLEFT
                if cx > w - b:
                    return _HTBOTTOMRIGHT
                return _HTBOTTOM
            if cx < b:
                return _HTLEFT
            if cx > w - b:
                return _HTRIGHT

        return user32.CallWindowProcW(old_proc, h, msg, wp, lp)

    # Keep the callback alive to prevent GC
    _install_resize_hook._ref = new_proc
    user32.SetWindowLongPtrW(hwnd, _GWL_WNDPROC, new_proc)


class _DesktopApi:
    """JS-exposed API for desktop-specific window operations and Spotify
    OAuth child-window flow."""

    def __init__(self, base_url: str):
        self._parent = None  # set after create_window
        self._base_url = base_url
        self._auth_child = None

    # -- Window controls -------------------------------------------------

    def minimize_window(self):
        if self._parent:
            self._parent.minimize()

    def toggle_maximize(self) -> bool:
        """Toggle maximized / restored state.  Returns True if now maximized."""
        if sys.platform != "win32":
            return False
        user32 = ctypes.windll.user32
        hwnd = _find_hwnd()
        if not hwnd:
            return False
        if self.is_maximized():
            user32.ShowWindow(hwnd, _SW_RESTORE)
            return False
        x, y, w, h = _get_work_area()
        user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0040)  # SWP_SHOWWINDOW
        return True

    def is_maximized(self) -> bool:
        if sys.platform != "win32":
            return False
        hwnd = _find_hwnd()
        if not hwnd:
            return False
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        wa = _get_work_area()
        return (rect.left == wa[0] and rect.top == wa[1]
                and rect.right - rect.left == wa[2]
                and rect.bottom - rect.top == wa[3])

    def close_window(self):
        if self._parent:
            self._parent.destroy()

    def save_profile_export(self, json_str: str) -> str:
        """Write profile JSON to user's Downloads folder. Returns the file path."""
        downloads = Path.home() / "Downloads"
        dest = downloads / "spotyvibe_profile.json"
        dest.write_text(json_str, encoding="utf-8")
        return str(dest)

    # -- Spotify OAuth child window --------------------------------------

    def open_spotify_auth(self):
        """Open Spotify OAuth in a child window, keeping the main window intact."""
        import webview  # noqa: WPS433

        if self._auth_child is not None:
            try:
                self._auth_child.destroy()
            except Exception:
                pass
            self._auth_child = None

        child = webview.create_window(
            title="Connect to Spotify",
            url=f"{self._base_url}/api/spotify/auth",
            width=500,
            height=700,
        )
        self._auth_child = child

        def _on_loaded():
            url = (child.get_current_url() or "")
            if "/callback" not in url:
                return
            if "error=" in url:
                return
            threading.Timer(1.5, self._finish_auth).start()

        child.events.loaded += _on_loaded

    def _finish_auth(self):
        child = self._auth_child
        self._auth_child = None
        if child is not None:
            try:
                child.destroy()
            except Exception:
                pass
        if self._parent is not None:
            try:
                self._parent.evaluate_js(
                    'window.dispatchEvent(new MessageEvent("message",'
                    '{data:"spotify-auth-complete"}))'
                )
            except Exception:
                pass


def _wait_for_server(host: str, port: int, timeout_s: float = 15.0) -> bool:
    """Block until the Flask server accepts connections (or timeout)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"

    flask_thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()

    if not _wait_for_server(host, port):
        print("ERROR: Flask server did not start within timeout.")
        return

    import webview  # noqa: WPS433 — imported late so Flask starts first

    api = _DesktopApi(base_url=url)

    if sys.platform == "win32":
        _user32 = ctypes.windll.user32
        screen_w = _user32.GetSystemMetrics(0)
        screen_h = _user32.GetSystemMetrics(1)
        win_w = min(int(screen_w * 0.80), 1600)
        win_h = min(int(screen_h * 0.75), 950)
    else:
        win_w, win_h = 1280, 900

    window = webview.create_window(
        title="SpotyVibe",
        url=url,
        width=win_w,
        height=win_h,
        min_size=(800, 600),
        text_select=True,
        frameless=True,
        # easy_drag defaults to True for frameless windows, which hijacks
        # mousedown+mousemove across the whole viewport to drag the OS
        # window — breaking text selection, drag-to-select, and any page
        # gesture that uses a mouse drag.  We provide our own drag surface
        # via `-webkit-app-region: drag` on #desktop-titlebar in _CHROME_JS,
        # which WebView2 handles natively via WM_NCHITTEST → HTCAPTION.
        easy_drag=False,
        js_api=api,
    )
    api._parent = window

    # Inject custom title bar + side frames after the page loads.
    window.events.loaded += lambda: window.evaluate_js(_CHROME_JS)

    # Apply DWM dark-mode styling, install resize hook, maximize, and sync
    # icon.  The `shown` event can fire before `loaded` (which injects the
    # title bar), so the JS must guard against dt-max-btn not existing yet.
    def _on_shown():
        _apply_dark_chrome()
        hwnd = _find_hwnd()
        if hwnd:
            _install_resize_hook(hwnd)
        api.toggle_maximize()
        window.evaluate_js(
            "var _b = document.getElementById('dt-max-btn');"
            "if (_b) {"
            "_b.innerHTML = "
            "'<svg width=\"12\" height=\"12\" viewBox=\"0 0 12 12\">"
            "<rect x=\"1\" y=\"3\" width=\"8\" height=\"8\" rx=\".5\" stroke=\"currentColor\" stroke-width=\"1\" fill=\"none\"/>"
            "<polyline points=\"3,3 3,1 11,1 11,9 9,9\" stroke=\"currentColor\" stroke-width=\"1\" fill=\"none\"/></svg>';"
            "_b.setAttribute(\"aria-label\", \"Restore\");"
            "}"
        )

    window.events.shown += _on_shown

    webview.start(storage_path=_get_storage_path())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # With console=False the user can't see stderr — write to a crash log.
        crash_log = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "spotyvibe" / "crash.log"
        crash_log.parent.mkdir(parents=True, exist_ok=True)
        import traceback as _tb
        crash_log.write_text(_tb.format_exc(), encoding="utf-8")
        raise
