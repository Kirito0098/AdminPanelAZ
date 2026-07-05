"""Shared TTF font resolution for Pillow image rendering (Cyrillic support)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_BUNDLED_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"

_SANS_FILES = {
    False: (
        _BUNDLED_DIR / "LiberationSans-Regular.ttf",
        _BUNDLED_DIR / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ),
    True: (
        _BUNDLED_DIR / "LiberationSans-Bold.ttf",
        _BUNDLED_DIR / "DejaVuSans-Bold.ttf",
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
}

_MONO_FILES = (
    _BUNDLED_DIR / "LiberationMono-Regular.ttf",
    Path("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"),
    _BUNDLED_DIR / "DejaVuSans.ttf",
)


@lru_cache(maxsize=16)
def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def load_image_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _first_existing(_SANS_FILES[bold])
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    if bold:
        regular = _first_existing(_SANS_FILES[False])
        if regular is not None:
            try:
                return ImageFont.truetype(str(regular), size)
            except OSError:
                pass
    raise RuntimeError(
        "Cyrillic-capable UI font not found. Bundle LiberationSans or DejaVuSans under backend/static/fonts/"
    )


def load_mono_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _first_existing(_MONO_FILES)
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return load_image_font(size, bold=False)
