from decimal import Decimal
from io import BytesIO

import zxingcpp
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from PIL import Image, ImageChops

from registrations.vietqr import build_vietqr, crc16, render_vietqr_png


def decode_tlv(payload):
    fields = {}
    offset = 0
    while offset < len(payload):
        tag = payload[offset : offset + 2]
        length = int(payload[offset + 2 : offset + 4])
        start = offset + 4
        end = start + length
        if len(tag) != 2 or end > len(payload) or tag in fields:
            raise AssertionError("Malformed or duplicate TLV field")
        fields[tag] = payload[start:end]
        offset = end
    return fields


class VietQrTests(SimpleTestCase):
    def test_crc_known_vector(self):
        # CRC-16/CCITT-FALSE standard check value, derived independently of VietQR.
        self.assertEqual(crc16(b"123456789"), "29B1")

    def test_exact_transfer_vector(self):
        # Published by the referenced subiz/vietqr generator for these inputs.
        payload, includes_content = build_vietqr(
            bank_bin="970415",
            account_number="0011001932418",
            amount=Decimal("120000"),
            transfer_content="ung ho lu lut",
        )

        self.assertTrue(includes_content)
        self.assertEqual(
            payload,
            "00020101021238570010A0000007270127000697041501130011001932418"
            "0208QRIBFTTA530370454061200005802VN62170813ung ho lu lut6304C15C",
        )

    def test_content_boundary_is_exact_and_long_content_is_omitted(self):
        exact_content = "A" * 25
        exact_payload, exact_includes_content = build_vietqr(
            bank_bin="970415",
            account_number="0062001932418",
            amount=Decimal("62"),
            transfer_content=exact_content,
        )
        long_payload, long_includes_content = build_vietqr(
            bank_bin="970415",
            account_number="0062001932418",
            amount=Decimal("62"),
            transfer_content="B" * 26,
        )

        self.assertTrue(exact_includes_content)
        self.assertEqual(
            decode_tlv(decode_tlv(exact_payload)["62"])["08"], exact_content
        )
        self.assertFalse(long_includes_content)
        self.assertNotIn("62", decode_tlv(long_payload))

    def test_non_ascii_content_is_omitted_without_replacement(self):
        payload, includes_content = build_vietqr(
            bank_bin="970415",
            account_number="0011001932418",
            amount=Decimal("1"),
            transfer_content="thanh toán",
        )

        self.assertFalse(includes_content)
        self.assertNotIn("thanh toan", payload)

    def test_destination_boundaries_preserve_leading_zeroes(self):
        payload, _ = build_vietqr(
            bank_bin="970415",
            account_number="0" * 19,
            amount=Decimal("1"),
            transfer_content="",
        )

        self.assertIn("0119" + "0" * 19, payload)
        for bank_bin in ("97041", "9704150", "97041A", "９７０４１５"):
            with self.subTest(bank_bin=bank_bin), self.assertRaises(ValidationError):
                build_vietqr(
                    bank_bin=bank_bin,
                    account_number="0011001932418",
                    amount=Decimal("1"),
                    transfer_content="",
                )
        for account_number in ("", "1" * 20, "0011 0019", "tài-khoản"):
            with (
                self.subTest(account_number=account_number),
                self.assertRaises(ValidationError),
            ):
                build_vietqr(
                    bank_bin="970415",
                    account_number=account_number,
                    amount=Decimal("1"),
                    transfer_content="",
                )

    def test_amount_must_be_positive_whole_dong_with_at_most_13_digits(self):
        for amount in (
            Decimal("0"),
            Decimal("-1"),
            Decimal("1.5"),
            Decimal("10000000000000"),
            Decimal("NaN"),
            Decimal("Infinity"),
        ):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                build_vietqr(
                    bank_bin="970415",
                    account_number="0011001932418",
                    amount=amount,
                    transfer_content="",
                )

    def test_rendered_png_decodes_to_payload_and_keeps_quiet_zone(self):
        payload, _ = build_vietqr(
            bank_bin="970415",
            account_number="0011001932418",
            amount=Decimal("120000"),
            transfer_content="ung ho lu lut",
        )

        image = Image.open(
            BytesIO(render_vietqr_png(payload=payload, copy_transfer_content=False))
        )
        decoded = zxingcpp.read_barcode(image, formats=zxingcpp.BarcodeFormat.QRCode)

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.text, payload)
        self.assertEqual(image.getpixel((0, 0)), 255)

    def test_fallback_png_has_readable_instruction_below_decodable_qr(self):
        payload, _ = build_vietqr(
            bank_bin="970415",
            account_number="0011001932418",
            amount=Decimal("120000"),
            transfer_content="",
        )
        plain = Image.open(
            BytesIO(render_vietqr_png(payload=payload, copy_transfer_content=False))
        )
        annotated = Image.open(
            BytesIO(render_vietqr_png(payload=payload, copy_transfer_content=True))
        )
        decoded = zxingcpp.read_barcode(
            annotated, formats=zxingcpp.BarcodeFormat.QRCode
        )

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.text, payload)
        self.assertEqual(annotated.width, plain.width)
        self.assertGreater(annotated.height, plain.height)
        annotation_region = annotated.crop(
            (0, plain.height, annotated.width, annotated.height)
        )
        self.assertEqual(annotation_region.getextrema()[0], 0)
        instruction_bounds = ImageChops.invert(annotation_region).getbbox()
        self.assertGreater(instruction_bounds[0], 0)
        self.assertLess(instruction_bounds[2], annotated.width)
        self.assertEqual(
            annotated.crop(
                (0, annotated.height - 8, annotated.width, annotated.height)
            ).getextrema(),
            (255, 255),
        )
