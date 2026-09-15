"""Private, exclusively created files for disposable browser fixtures."""

import json
import os
from pathlib import Path


def write_private_fixture(path: Path, payload: dict) -> None:
    # O_EXCL atomically rejects existing paths (including symlinks); permissions
    # apply at creation, before any capability bytes are written.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(payload, stream)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
