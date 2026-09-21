import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase
from e2e.fixtures import write_private_fixture


class PrivateFixtureTests(SimpleTestCase):
    def test_file_is_private_at_creation_even_with_permissive_umask(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            real_fdopen = os.fdopen
            observed = []

            def inspect_fd(fd, *args, **kwargs):
                observed.append(os.fstat(fd).st_mode & 0o777)
                return real_fdopen(fd, *args, **kwargs)

            old_umask = os.umask(0)
            try:
                with patch("e2e.fixtures.os.fdopen", side_effect=inspect_fd):
                    write_private_fixture(path, {"credential": "synthetic"})
            finally:
                os.umask(old_umask)
            self.assertEqual(observed, [0o600])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), {"credential": "synthetic"})

    def test_preexisting_file_and_symlink_are_never_followed_or_overwritten(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.write_text("original")
            link = Path(directory) / "fixture.json"
            link.symlink_to(target)
            for path in (target, link):
                with self.assertRaises(FileExistsError):
                    write_private_fixture(path, {"credential": "synthetic"})
            self.assertEqual(target.read_text(), "original")
            self.assertTrue(link.is_symlink())

    def test_failed_write_removes_only_its_new_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            with self.assertRaises(TypeError):
                write_private_fixture(path, {"not_json": object()})
            self.assertFalse(path.exists())
