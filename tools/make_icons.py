"""Generate cross-platform application icons from a single source PNG.

Produces, from ``src/icons/cpm-fm-2.png``:

* ``assets/icon.ico``  — Windows (multi-resolution: 16/24/32/48/64/128/256)
* ``assets/icon.icns`` — macOS (16..1024, including @2x retina variants)
* ``assets/icon.png``  — Linux primary (512x512)
* ``assets/icons/hicolor/<size>x<size>/apps/cpm-fm.png`` — Linux icon-theme PNGs
* ``src/cpm_fm/icons/cpm-fm.png`` — runtime window/taskbar icon, shipped as
  package data and loaded at start-up (UIR-078, DR-044)

The source is not square, so it is first padded to a centred, transparent
square before any resampling, which keeps the artwork undistorted.

Usage:  python tools/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "icons" / "cpm-fm-2.png"
ASSETS = ROOT / "assets"
# DR-044: the runtime window icon ships as package data under the cpm_fm
# package so it is resolvable both in a source checkout and a frozen bundle.
RUNTIME_ICON = ROOT / "src" / "cpm_fm" / "icons" / "cpm-fm.png"
RUNTIME_ICON_SIZE = 256

# Square sizes shared by the various targets.
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]
LINUX_THEME_SIZES = [16, 24, 32, 48, 64, 128, 256, 512]


def load_square_master(path: Path) -> Image.Image:
    """Load the source image and pad it to a centred, transparent square."""
    img = Image.open(path).convert("RGBA")
    side = max(img.width, img.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def resized(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), Image.LANCZOS)


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Source image not found: {SOURCE}")

    ASSETS.mkdir(parents=True, exist_ok=True)
    master = load_square_master(SOURCE)
    print(f"Source {SOURCE.name}: {Image.open(SOURCE).size} -> square {master.size}")

    # Windows .ico (embeds all sizes in one file).
    ico_path = ASSETS / "icon.ico"
    master.save(ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"Wrote {ico_path.relative_to(ROOT)}  sizes={ICO_SIZES}")

    # macOS .icns.
    icns_path = ASSETS / "icon.icns"
    # Pillow derives the ICNS members from the largest image it is given.
    resized(master, 1024).save(icns_path, format="ICNS")
    print(f"Wrote {icns_path.relative_to(ROOT)}  sizes={ICNS_SIZES}")

    # Linux primary PNG.
    png_path = ASSETS / "icon.png"
    resized(master, 512).save(png_path, format="PNG")
    print(f"Wrote {png_path.relative_to(ROOT)}  size=512")

    # Linux freedesktop icon-theme tree.
    for s in LINUX_THEME_SIZES:
        out = ASSETS / "icons" / "hicolor" / f"{s}x{s}" / "apps" / "cpm-fm.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        resized(master, s).save(out, format="PNG")
    print(
        f"Wrote {len(LINUX_THEME_SIZES)} theme PNGs under "
        f"{(ASSETS / 'icons' / 'hicolor').relative_to(ROOT)}"
    )

    # Runtime window/taskbar icon, shipped as cpm_fm package data (UIR-078).
    RUNTIME_ICON.parent.mkdir(parents=True, exist_ok=True)
    resized(master, RUNTIME_ICON_SIZE).save(RUNTIME_ICON, format="PNG")
    print(f"Wrote {RUNTIME_ICON.relative_to(ROOT)}  size={RUNTIME_ICON_SIZE}")


if __name__ == "__main__":
    main()
