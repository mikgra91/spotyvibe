"""Build-time helper: generate a Windows .ico from the Android launcher PNG.

This avoids adding binary assets to the repo while keeping the build
process deterministic.

Implementation note:
- Writes an ICO which embeds a single PNG image (supported by Windows Vista+).
- Does not require Pillow.
"""

from __future__ import annotations

import struct
from pathlib import Path


def main() -> None:
    src = Path("android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png")
    dst = Path("build_assets/spotyvibe.ico")

    if not src.exists():
        raise SystemExit(f"Source icon not found: {src}")

    png = src.read_bytes()

    # ICO structure (single image):
    # ICONDIR: reserved (2) + type (2) + count (2)
    header = struct.pack("<HHH", 0, 1, 1)

    # ICONDIRENTRY (16 bytes)
    # width, height: 1 byte each (0 means 256)
    # color_count, reserved: 1 byte each
    # planes, bit_count: 2 bytes each
    # bytes_in_res: 4 bytes
    # image_offset: 4 bytes
    width = 192
    height = 192
    entry = struct.pack(
        "<BBBBHHII",
        width if width < 256 else 0,
        height if height < 256 else 0,
        0,
        0,
        1,
        32,
        len(png),
        6 + 16,  # header (6) + entry (16)
    )

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(header + entry + png)

    print(f"Wrote: {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
