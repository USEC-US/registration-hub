from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image, PngImagePlugin

from registrations.images import prepare_payment_image

from .images import payment_image


class PaymentImageTests(SimpleTestCase):
    def test_accepts_the_size_limit_and_removes_trailing_data(self):
        content = payment_image().read()
        upload = SimpleUploadedFile(
            "proof.png", content + b"x" * (10 * 1024 * 1024 - len(content))
        )
        prepared = prepare_payment_image(upload)
        self.assertLess(prepared.size, 1024)
        self.assertEqual(Image.open(prepared).size, (4, 4))

    def test_discards_embedded_metadata(self):
        data = BytesIO()
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private", "secret location")
        Image.new("RGB", (4, 4)).save(data, format="PNG", pnginfo=metadata)
        prepared = prepare_payment_image(
            SimpleUploadedFile("proof.png", data.getvalue())
        )
        self.assertNotIn(b"secret location", prepared.read())

    def test_preserves_phone_photo_orientation_while_removing_exif(self):
        data = BytesIO()
        image = Image.new("RGB", (4, 8))
        exif = image.getexif()
        exif[274] = 6
        image.save(data, format="JPEG", exif=exif)
        prepared = prepare_payment_image(
            SimpleUploadedFile("proof.jpg", data.getvalue())
        )
        with Image.open(prepared) as result:
            self.assertEqual(result.size, (8, 4))
            self.assertFalse(result.getexif())

    def test_rejects_images_above_the_pixel_limit(self):
        data = BytesIO()
        Image.new("1", (5000, 4001)).save(data, format="PNG")
        with self.assertRaises(ValidationError):
            prepare_payment_image(SimpleUploadedFile("proof.png", data.getvalue()))
