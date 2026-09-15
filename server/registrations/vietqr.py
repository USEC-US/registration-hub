"""Strict local VietQR payload construction and PNG rendering."""

from decimal import Decimal
from io import BytesIO
import re

from django.core.exceptions import ValidationError
from PIL import Image, ImageDraw, ImageFont
import qrcode


_ASCII_ACCOUNT = re.compile(r"[0-9A-Za-z]{1,19}\Z", re.ASCII)
_ASCII_BIN = re.compile(r"[0-9]{6}\Z", re.ASCII)
_TRANSFER_CONTENT_LIMIT = 25


def crc16(data: bytes) -> str:
    """Return CRC-16/CCITT-FALSE as four uppercase hexadecimal characters."""
    checksum = 0xFFFF
    for byte in data:
        checksum ^= byte << 8
        for _ in range(8):
            checksum = (
                ((checksum << 1) ^ 0x1021) & 0xFFFF
                if checksum & 0x8000
                else (checksum << 1) & 0xFFFF
            )
    return f"{checksum:04X}"


def _tlv(tag: str, value: str) -> str:
    if not re.fullmatch(r"[0-9]{2}", tag, flags=re.ASCII):
        raise ValidationError("VietQR tags must be two ASCII digits.")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValidationError(
            "VietQR values must use supported ASCII syntax."
        ) from error
    if len(encoded) > 99:
        raise ValidationError("VietQR values cannot exceed a two-digit length.")
    return f"{tag}{len(encoded):02d}{value}"


def _amount_text(amount: Decimal) -> str:
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise ValidationError("VietQR amount must be a finite Decimal value.")
    if amount <= 0 or amount != amount.to_integral_value():
        raise ValidationError("VND amount must be a positive whole-dong value.")
    value = str(int(amount))
    if len(value) > 13:
        raise ValidationError("VietQR amount cannot exceed 13 digits.")
    return value


def build_vietqr(
    *, bank_bin: str, account_number: str, amount: Decimal, transfer_content: str
) -> tuple[str, bool]:
    """Build an exact dynamic-account VietQR payload without truncating inputs."""
    if not _ASCII_BIN.fullmatch(bank_bin):
        raise ValidationError("Bank BIN must contain exactly six ASCII digits.")
    if not _ASCII_ACCOUNT.fullmatch(account_number):
        raise ValidationError(
            "Account number must contain 1 to 19 ASCII letters or digits."
        )

    merchant = (
        _tlv("00", "A000000727")
        + _tlv("01", _tlv("00", bank_bin) + _tlv("01", account_number))
        + _tlv("02", "QRIBFTTA")
    )
    payload = (
        _tlv("00", "01")
        + _tlv("01", "12")
        + _tlv("38", merchant)
        + _tlv("53", "704")
        + _tlv("54", _amount_text(amount))
        + _tlv("58", "VN")
    )

    includes_content = False
    if transfer_content:
        try:
            content_bytes = transfer_content.encode("ascii")
        except UnicodeEncodeError:
            content_bytes = b""
        if content_bytes and len(content_bytes) <= _TRANSFER_CONTENT_LIMIT:
            payload += _tlv("62", _tlv("08", transfer_content))
            includes_content = True

    payload += "6304"
    return payload + crc16(payload.encode("ascii")), includes_content


def _instruction_font():
    try:
        return ImageFont.truetype("DejaVuSans.ttf", 14)
    except OSError:
        return ImageFont.load_default()


def render_vietqr_png(*, payload: str, copy_transfer_content: bool) -> bytes:
    """Render a local QR PNG, with a copy/paste warning for fallback payloads."""
    try:
        payload.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValidationError("VietQR payload must contain only ASCII data.") from error

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("L")

    if copy_transfer_content:
        lines = (
            "QR khong co noi dung chuyen khoan.",
            "Sao chep day du noi dung chuyen khoan",
            "vao ung dung ngan hang.",
            "QR does not include transfer content.",
            "Paste the full content in your bank app.",
        )
        font = _instruction_font()
        draw = ImageDraw.Draw(image)
        line_boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        line_heights = [box[3] - box[1] for box in line_boxes]
        padding = 16
        gap = 8
        annotation_height = padding * 2 + sum(line_heights) + gap * (len(lines) - 1)
        annotated = Image.new(
            "L", (image.width, image.height + annotation_height), color="white"
        )
        annotated.paste(image, (0, 0))
        annotation_draw = ImageDraw.Draw(annotated)
        y = image.height + padding
        for line, box, height in zip(lines, line_boxes, line_heights, strict=True):
            width = box[2] - box[0]
            annotation_draw.text(
                ((image.width - width) // 2 - box[0], y - box[1]),
                line,
                fill="black",
                font=font,
            )
            y += height + gap
        image = annotated

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
