import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils.helpers import safe_remove
from utils.safe_paths import destructive_absolute, overwrite_file


class SafePathTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX system aliases")
    def test_macos_standard_alias_accepts_relative_and_absolute_destinations(self):
        with patch("utils.safe_paths.sys.platform", "darwin"), patch.object(Path, "is_symlink", return_value=True):
            for name in ("var", "tmp", "etc"):
                for destination in (f"private/{name}", f"/private/{name}"):
                    with self.subTest(name=name, destination=destination), patch("utils.safe_paths.os.readlink", return_value=destination):
                        self.assertEqual(destructive_absolute(Path(f"/{name}/selected")), Path(f"/private/{name}/selected"))
            with patch("utils.safe_paths.os.readlink", return_value="/untrusted"):
                self.assertEqual(destructive_absolute(Path("/var/selected")), Path("/var/selected"))

    def test_regular_file_can_be_overwritten_and_tree_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            tree = Path(folder) / "selected"
            tree.mkdir()
            file = tree / "file"
            file.write_bytes(b"original")
            with overwrite_file(file) as stream:
                stream.write(b"changed!")
            self.assertEqual(file.read_bytes(), b"changed!")
            self.assertTrue(safe_remove(tree))
            self.assertFalse(tree.exists())

    @unittest.skipUnless(os.name == "posix", "POSIX descriptor paths")
    def test_ancestor_replacement_never_opens_outside_file(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            selected, outside = base / "selected", base / "outside"
            selected.mkdir(); outside.mkdir()
            (selected / "file").write_bytes(b"selected")
            protected = outside / "file"
            protected.write_bytes(b"outside")
            selected.rename(base / "moved")
            selected.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(OSError):
                with overwrite_file(selected / "file"):
                    self.fail("followed an ancestor alias")
            self.assertFalse(safe_remove(selected))
            self.assertEqual(protected.read_bytes(), b"outside")

    @unittest.skipUnless(os.name == "posix", "POSIX file identity")
    def test_open_descriptor_stays_on_selected_file_after_parent_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            selected, outside = base / "selected", base / "outside"
            selected.mkdir(); outside.mkdir()
            (selected / "file").write_bytes(b"selected")
            protected = outside / "file"
            protected.write_bytes(b"outside")
            with overwrite_file(selected / "file") as stream:
                selected.rename(base / "moved")
                selected.symlink_to(outside, target_is_directory=True)
                stream.write(b"changed!")
            self.assertEqual(protected.read_bytes(), b"outside")
            self.assertEqual((base / "moved" / "file").read_bytes(), b"changed!")
