import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from footprint.browser import _browser_targets
from footprint.shell import _history_targets
from footprint.system import _clean_flatpak_cache, _clean_temp_files, _system_targets
from utils.platform_utils import OS, appdata_dir, cache_dir, current_os, temp_dir


class PlatformDetectionTests(unittest.TestCase):
    def test_supported_platform_names_are_mapped_explicitly(self):
        cases = {
            "Windows": OS.WINDOWS,
            "Darwin": OS.MACOS,
            "Linux": OS.LINUX,
            "Plan9": OS.UNKNOWN,
        }
        for platform_name, expected in cases.items():
            with self.subTest(platform=platform_name):
                with patch("utils.platform_utils.platform.system", return_value=platform_name):
                    self.assertEqual(current_os(), expected)

    def test_temp_directory_uses_runtime_user_directory(self):
        with tempfile.TemporaryDirectory() as runtime_temp:
            with patch(
                "utils.platform_utils.tempfile.gettempdir", return_value=runtime_temp
            ):
                self.assertEqual(temp_dir(), Path(runtime_temp).resolve())

    def test_linux_honors_xdg_directories(self):
        with (
            patch("utils.platform_utils.current_os", return_value=OS.LINUX),
            patch.dict(
                "os.environ",
                {
                    "XDG_CONFIG_HOME": "/custom/config",
                    "XDG_CACHE_HOME": "/custom/cache",
                },
                clear=False,
            ),
        ):
            self.assertEqual(appdata_dir(), Path("/custom/config"))
            self.assertEqual(cache_dir(), Path("/custom/cache"))


class PlatformTargetTests(unittest.TestCase):
    def test_unknown_platform_has_no_linux_cleanup_fallback(self):
        flag_patches = (
            patch("footprint.browser.is_windows", return_value=False),
            patch("footprint.browser.is_macos", return_value=False),
            patch("footprint.browser.is_linux", return_value=False),
            patch("footprint.shell.is_windows", return_value=False),
            patch("footprint.shell.is_macos", return_value=False),
            patch("footprint.shell.is_linux", return_value=False),
            patch("footprint.system.is_windows", return_value=False),
            patch("footprint.system.is_macos", return_value=False),
            patch("footprint.system.is_linux", return_value=False),
        )
        for active_patch in flag_patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

        self.assertEqual(_browser_targets(), [])
        self.assertEqual(_history_targets(), [])
        self.assertEqual(_system_targets(), [])

    def test_each_supported_platform_builds_cleanup_targets(self):
        modules = ("footprint.browser", "footprint.shell", "footprint.system")
        functions = (_browser_targets, _history_targets, _system_targets)
        for selected in ("windows", "macos", "linux"):
            for module, target_function in zip(modules, functions):
                with self.subTest(platform=selected, module=module):
                    with (
                        patch(f"{module}.is_windows", return_value=selected == "windows"),
                        patch(f"{module}.is_macos", return_value=selected == "macos"),
                        patch(f"{module}.is_linux", return_value=selected == "linux"),
                    ):
                        self.assertGreater(len(target_function()), 0)

    def test_linux_browser_targets_include_separate_xdg_cache(self):
        with (
            patch("footprint.browser.is_windows", return_value=False),
            patch("footprint.browser.is_macos", return_value=False),
            patch("footprint.browser.is_linux", return_value=True),
            patch("footprint.browser.home", return_value=Path("/home/tester")),
            patch("footprint.browser.appdata_dir", return_value=Path("/xdg/config")),
            patch("footprint.browser.cache_dir", return_value=Path("/xdg/cache")),
        ):
            targets = {name: path for name, path, _subdirs in _browser_targets()}

        self.assertEqual(targets["Google Chrome"], Path("/xdg/config/google-chrome"))
        self.assertEqual(
            targets["Google Chrome (Cache)"], Path("/xdg/cache/google-chrome")
        )

    def test_flatpak_cache_uses_current_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / ".var" / "app"
            cache = base / "org.example.App" / "cache"
            cache.mkdir(parents=True)
            (cache / "item.bin").write_bytes(b"cache")

            results = _clean_flatpak_cache(base, dry_run=True)

        self.assertEqual([Path(item["path"]) for item in results], [cache])

    def test_temp_cleanup_rejects_critical_directory_override(self):
        with (
            patch("footprint.system.temp_dir", return_value=Path.home()),
            patch("footprint.system.is_windows", return_value=True),
            patch("footprint.system.safe_remove") as remove,
        ):
            results = _clean_temp_files(dry_run=False)

        self.assertEqual(results, [])
        remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
