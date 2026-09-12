from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def payment_image(format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format=format)
    return SimpleUploadedFile(
        f"proof.{format.lower()}",
        buffer.getvalue(),
        content_type=f"image/{format.lower()}",
    )
