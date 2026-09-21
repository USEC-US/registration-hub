import posixpath

from django.http import Http404
from django.views.static import serve


def serve_public_media(request, path, **kwargs):
    # Match Django's path normalization before excluding private proof files.
    normalized = posixpath.normpath(path).lstrip("/")
    if normalized == "payment-proofs" or normalized.startswith("payment-proofs/"):
        raise Http404
    return serve(request, normalized, **kwargs)
