"""Generate the PyInstaller startup splash image (build_assets/splash.png).

The onefile EXE bootloader shows this image immediately while it extracts the
bundle to a temp directory (a multi-second, feedback-free wait otherwise). The
launcher updates the status line at the bottom via ``pyi_splash.update_text``.

Run once whenever the branding changes:

    python build-tools/make_splash.py

Requires Pillow (already a transitive build dependency via pytest-playwright).
The generated PNG is committed so normal builds do not need Pillow.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 480, 260
BG = (5, 6, 8)            # #050608  — matches app --bg-main
GREEN = (29, 185, 84)     # #1DB954  — Spotify green wordmark
GREY = (150, 150, 150)    # subtitle / status text
FAINT = (40, 44, 48)      # accent rule


def _font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for name in names:
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _centered(draw: ImageDraw.ImageDraw, y: int, text: str,
              font: ImageFont.FreeTypeFont, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((W - (right - left)) / 2 - left, y), text, font=font, fill=fill)


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "build_assets", "splash.png")

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    wordmark = _font(["segoeuib.ttf", "seguisb.ttf", "segoeui.ttf"], 46)
    subtitle = _font(["segoeui.ttf"], 16)

    _centered(draw, 78, "SpotyVibe", wordmark, GREEN)
    _centered(draw, 140, "AI-powered music discovery", subtitle, GREY)

    # Thin accent rule above the status area.
    draw.line([(W * 0.30, 186), (W * 0.70, 186)], fill=FAINT, width=1)

    img.save(out, "PNG")
    print(f"Wrote {os.path.abspath(out)} ({W}x{H})")


if __name__ == "__main__":
    main()
