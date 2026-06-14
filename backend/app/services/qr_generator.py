import io

import qrcode
from qrcode.exceptions import DataOverflowError
from qrcode.image.pil import PilImage


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
    try:
        _build_qr(config_text)
    except ValueError:
        return False
    return True


def generate_qr_png(config_text: str) -> bytes:
    qr = _build_qr(config_text)

    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
