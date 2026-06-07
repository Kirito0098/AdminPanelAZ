"""Captcha generation for login brute-force protection."""

from __future__ import annotations

import io
import random
import secrets
import string
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

CAPTCHA_STORE: dict[str, dict] = {}
CAPTCHA_LOCK = threading.Lock()
CAPTCHA_TTL = 300


def _cleanup_captchas() -> None:
    now = time.time()
    with CAPTCHA_LOCK:
        stale = [k for k, v in CAPTCHA_STORE.items() if now - v.get("created", 0) > CAPTCHA_TTL]
        for k in stale:
            CAPTCHA_STORE.pop(k, None)


class CaptchaService:
    def __init__(self, font_path: str | None = None):
        default_font = Path(__file__).resolve().parents[2] / "static" / "fonts" / "DejaVuSans-Bold.ttf"
        self.font_path = font_path or str(default_font)

    def generate_text(self) -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    def create_captcha(self) -> tuple[str, bytes]:
        _cleanup_captchas()
        captcha_id = secrets.token_hex(16)
        text = self.generate_text()
        with CAPTCHA_LOCK:
            CAPTCHA_STORE[captcha_id] = {"text": text, "created": time.time()}
        return captcha_id, self._render_image(text)

    def verify(self, captcha_id: str, user_input: str) -> bool:
        _cleanup_captchas()
        with CAPTCHA_LOCK:
            entry = CAPTCHA_STORE.pop(captcha_id, None)
        if not entry:
            return False
        return (user_input or "").strip().upper() == entry.get("text", "")

    def _render_image(self, text: str) -> bytes:
        width, height = 200, 60
        image = Image.new("RGB", (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype(self.font_path, 36)
        except OSError:
            font = ImageFont.load_default()
        x_offset = 20
        for char in text:
            angle = random.randint(-12, 12)
            char_img = Image.new("RGBA", (40, 50), (255, 255, 255, 0))
            char_draw = ImageDraw.Draw(char_img)
            char_draw.text((0, 0), char, font=font, fill=(0, 0, 0))
            char_img = char_img.rotate(angle, expand=1, resample=Image.BICUBIC)
            image.paste(char_img, (x_offset, 10), char_img)
            x_offset += 28
        for _ in range(120):
            x, y = random.randint(0, width), random.randint(0, height)
            draw.ellipse((x, y, x + 2, y + 2), fill=(200, 200, 200))
        image = image.filter(ImageFilter.GaussianBlur(radius=0.4))
        image = ImageEnhance.Contrast(image).enhance(1.4)
        buf = io.BytesIO()
        image.save(buf, "PNG")
        return buf.getvalue()


captcha_service = CaptchaService()
