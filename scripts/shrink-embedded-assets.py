#!/usr/bin/env python3
"""Copy assets to public/ with smaller face/food images for embedded (UNO Q). Needs: pip install Pillow"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("shrink-embedded-assets: Pillow not installed, skipping (pip install Pillow)", file=sys.stderr)
    sys.exit(0)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets"
DST = ROOT / "public" / "assets"
MAX_FACE = 320
MAX_FOOD = 64
MAX_BG_W = 1280


def save_thumb(src: Path, dest: Path, max_px: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    im.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    im.save(dest, optimize=True)


def main() -> None:
    if not SRC.is_dir():
        return
    for name in ("background.png",):
        p = SRC / name
        if p.is_file():
            dest = DST / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            im = Image.open(p)
            w, h = im.size
            if w > MAX_BG_W:
                nh = int(h * MAX_BG_W / w)
                im = im.resize((MAX_BG_W, nh), Image.Resampling.LANCZOS)
            im.save(dest, optimize=True)
    faces = SRC / "faces"
    if faces.is_dir():
        for f in faces.glob("*.png"):
            save_thumb(f, DST / "faces" / f.name, MAX_FACE)
    foods = SRC / "foods"
    if foods.is_dir():
        for f in foods.glob("*.png"):
            save_thumb(f, DST / "foods" / f.name, MAX_FOOD)
    print("Embedded assets optimized in public/assets/")


if __name__ == "__main__":
    main()
