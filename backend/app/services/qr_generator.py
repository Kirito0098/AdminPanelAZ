import io
import re

import qrcode
from qrcode.exceptions import DataOverflowError
from qrcode.image.pil import PilImage

# Absolute QR capacity is ~2953 bytes (v40 / ECC L), but phone cameras rarely
# scan dense codes near that limit. Prefer download-link above this threshold.
PRACTICAL_QR_PROFILE_MAX_BYTES = 1200

_AZ_WG_AWG_PATH = re.compile(
    r"/(?:wireguard|amneziawg)/antizapret(?:[-/]|$)",
    re.IGNORECASE,
)


def _build_qr(config_text: str) -> qrcode.QRCode:
    correction_levels = (
        qrcode.constants.ERROR_CORRECT_H,
        qrcode.constants.ERROR_CORRECT_Q,
        qrcode.constants.ERROR_CORRECT_M,
        qrcode.constants.ERROR_CORRECT_L,
    )

    last_error = None
    for correction_level in correction_levels:
        try:
            candidate = qrcode.QRCode(
                version=None,
                error_correction=correction_level,
                box_size=10,
                border=4,
            )
            candidate.add_data(config_text)
            candidate.make(fit=True)
            return candidate
        except (DataOverflowError, ValueError) as exc:
            last_error = exc

    raise ValueError(f"Конфигурация слишком длинная для QR-кода: {last_error}")


def fits_in_qr(config_text: str) -> bool:
    """True if content can be encoded as a phone-scannable profile QR."""
    if len(config_text.encode("utf-8")) > PRACTICAL_QR_PROFILE_MAX_BYTES:
        return False
    try:
        _build_qr(config_text)
    except ValueError:
        return False
    return True


def prefers_download_link_qr(*, path: str, content: str) -> bool:
    """
    Prefer a one-time download URL in the QR instead of embedding the profile.

    AntiZapret WireGuard/AmneziaWG profiles carry huge AllowedIPs lists and never
    fit a usable single QR. OpenVPN .ovpn files embed certificates (~4.5KB+).
    """
    lowered = (path or "").replace("\\", "/").lower()
    if lowered.endswith(".ovpn"):
        return True
    if _AZ_WG_AWG_PATH.search(lowered):
        return True
    return not fits_in_qr(content)


def generate_qr_png(config_text: str) -> bytes:
    qr = _build_qr(config_text)

    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
