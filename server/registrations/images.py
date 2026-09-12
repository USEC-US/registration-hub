import warnings
from io import BytesIO
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PROOF_BYTES = 10 * 1024 * 1024
MAX_PROOF_PIXELS = 20_000_000
PROOF_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def prepare_payment_image(upload):
    """Decode and re-encode proof images, discarding metadata and trailing data."""
    if upload is None:
        raise ValidationError({"proof_file": "A payment proof image is required."})
    if not 0 < upload.size <= MAX_PROOF_BYTES:
        raise ValidationError({"proof_file": "Upload an image no larger than 10 MB."})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            upload.seek(0)
            with Image.open(upload) as image:
                format = image.format
                if format not in PROOF_FORMATS:
                    raise ValueError("Unsupported image format")
                if image.width * image.height > MAX_PROOF_PIXELS or getattr(
                    image, "is_animated", False
                ):
                    raise ValueError("Image is too large or animated")
                image.verify()
            upload.seek(0)
            with Image.open(upload) as image:
                image.load()
                # Copy pixels into a new image so EXIF and other metadata cannot survive.
                pixels = ImageOps.exif_transpose(image).convert(
                    "RGBA" if format != "JPEG" else "RGB"
                )
                clean = Image.new(pixels.mode, pixels.size)
                clean.paste(pixels)
                output = BytesIO()
                clean.save(output, format=format)
    except (
        OSError,
        ValueError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValidationError(
            {
                "proof_file": "Upload a valid, still JPEG, PNG, or WebP image (up to 20 megapixels)."
            }
        ) from error
    finally:
        upload.seek(0)
    if output.tell() > MAX_PROOF_BYTES:
        raise ValidationError(
            {"proof_file": "The processed image exceeds 10 MB. Use a smaller image."}
        )
    return ContentFile(output.getvalue(), name=f"{uuid4().hex}.{PROOF_FORMATS[format]}")
