from django.http import Http404
from django.test import RequestFactory, SimpleTestCase

from config.media import serve_public_media


class PublicMediaTests(SimpleTestCase):
    def test_private_files_cannot_be_reached_through_normalized_public_paths(self):
        for path in (
            "payment-proofs/proof.png",
            "other/../payment-proofs/proof.png",
            "/payment-proofs/proof.png",
        ):
            with self.subTest(path=path), self.assertRaises(Http404):
                serve_public_media(
                    RequestFactory().get("/media/"), path, document_root="/tmp"
                )
