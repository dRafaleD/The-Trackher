import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from osint.services import EMAIL_PLATFORMS_PATH
from osint.username_checker import PLATFORMS_PATH
from utils.app_paths import launcher_arguments, resource_path


class PackagingConfigTests(unittest.TestCase):
    def test_pyproject_exposes_trackher_entry_point(self):
        text = Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('name = "Trackher"', text)
        self.assertIn('trackher = "main:main"', text)
        self.assertIn('version = { attr = "utils.__version__" }', text)
        self.assertIn(
            'packages = ["assets", "footprint", "osint", "utils", "gui", "gui.tabs", "gui.widgets"]',
            text,
        )
        self.assertIn('py-modules = ["main", "setup_context_menu"]', text)
        self.assertIn(
            'assets = ["logo.jpg", "trackher-banner.png", "trackher-terminal.png"]',
            text,
        )
        self.assertIn('osint = ["*.json"]', text)

    def test_catalog_paths_exist(self):
        self.assertTrue(EMAIL_PLATFORMS_PATH.exists())
        self.assertTrue(PLATFORMS_PATH.exists())
        self.assertTrue(resource_path("assets", "logo.jpg").exists())
        self.assertTrue(resource_path("assets", "trackher-banner.png").exists())
        self.assertTrue(resource_path("assets", "trackher-terminal.png").exists())


class RuntimePathTests(unittest.TestCase):
    def test_launcher_arguments_use_main_script_in_source_mode(self):
        with (
            patch("utils.app_paths.is_frozen", return_value=False),
            patch("utils.app_paths.project_root", return_value=Path("C:/Trackher")),
            patch("utils.app_paths.sys.executable", "C:/Python/python.exe"),
        ):
            command = launcher_arguments("--version")

        self.assertEqual(command[0], "C:/Python/python.exe")
        self.assertEqual(command[1], str(Path("C:/Trackher") / "main.py"))
        self.assertEqual(command[2], "--version")

    def test_launcher_arguments_use_executable_when_frozen(self):
        with (
            patch("utils.app_paths.is_frozen", return_value=True),
            patch("utils.app_paths.sys.executable", "C:/Apps/Trackher/Trackher.exe"),
        ):
            command = launcher_arguments("--version")

        self.assertEqual(command[0], str(Path("C:/Apps/Trackher/Trackher.exe")))
        self.assertEqual(command[1], "--version")

    def test_resource_path_prefers_bundle_dir_when_frozen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir)
            bundled_asset = bundle / "assets" / "logo.jpg"
            bundled_asset.parent.mkdir(parents=True)
            bundled_asset.write_bytes(b"logo")

            with (
                patch("utils.app_paths.is_frozen", return_value=True),
                patch("utils.app_paths.bundle_root", return_value=bundle),
            ):
                resolved = resource_path("assets", "logo.jpg")

        self.assertEqual(resolved, bundled_asset)


if __name__ == "__main__":
    unittest.main()
