import argparse
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from footprint.browser import (
    _CHROMIUM_CACHE_DIRS,
    _clean_sqlite_db,
    clean_browser_data,
)
from main import positive_int
from utils.helpers import (
    collect_files,
    get_dir_size,
    load_exclusions,
    safe_remove,
)
from utils.reporter import export_to_html
from utils.scheduler import schedule_task


class ExclusionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        empty_config = self.base / "empty-exclusions.json"
        empty_config.write_text('{"exclude": []}', encoding="utf-8")
        load_exclusions(str(empty_config))
        self.temp_dir.cleanup()

    def load_exclusion(self, *paths: Path) -> int:
        config = self.base / "exclusions.json"
        config.write_text(
            json.dumps({"exclude": [str(path) for path in paths]}),
            encoding="utf-8",
        )
        return load_exclusions(str(config))

    def test_directory_cleanup_preserves_excluded_descendant(self):
        cache = self.base / "cache"
        protected = cache / "protected" / "keep.txt"
        removable = cache / "remove.txt"
        protected.parent.mkdir(parents=True)
        protected.write_bytes(b"keep")
        removable.write_bytes(b"remove-me")

        self.assertEqual(self.load_exclusion(protected), 1)
        self.assertEqual(get_dir_size(cache), len(b"remove-me"))
        self.assertTrue(safe_remove(cache))
        self.assertTrue(protected.exists())
        self.assertFalse(removable.exists())

    def test_excluded_root_is_never_removed(self):
        target = self.base / "protected"
        target.mkdir()
        (target / "data.txt").write_text("data", encoding="utf-8")
        self.load_exclusion(target)

        self.assertFalse(safe_remove(target))
        self.assertFalse(safe_remove(target, dry_run=True))
        self.assertTrue((target / "data.txt").exists())

    def test_collection_skips_excluded_files(self):
        root = self.base / "files"
        root.mkdir()
        kept = root / "keep.txt"
        found = root / "found.txt"
        kept.write_text("keep", encoding="utf-8")
        found.write_text("found", encoding="utf-8")
        self.load_exclusion(kept)

        self.assertEqual(collect_files(root, "*.txt"), [found])

    def test_invalid_exclusion_config_is_rejected(self):
        config = self.base / "invalid.json"
        config.write_text('{"exclude": [""]}', encoding="utf-8")

        with self.assertRaises(ValueError):
            load_exclusions(str(config))


class SqliteCleaningTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        config = self.base / "empty-exclusions.json"
        config.write_text('{"exclude": []}', encoding="utf-8")
        load_exclusions(str(config))

    def tearDown(self):
        config = self.base / "empty-exclusions.json"
        config.write_text('{"exclude": []}', encoding="utf-8")
        load_exclusions(str(config))
        self.temp_dir.cleanup()

    def create_database(self) -> Path:
        db_path = self.base / "History"
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT)")
            connection.executemany(
                "INSERT INTO urls(url) VALUES (?)",
                [(f"https://example.com/{index}/" + "x" * 200,) for index in range(500)],
            )
            connection.commit()
        finally:
            connection.close()
        return db_path

    def row_count(self, db_path: Path) -> int:
        connection = sqlite3.connect(db_path)
        try:
            return connection.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
        finally:
            connection.close()

    def test_sqlite_cleanup_reports_real_size_difference(self):
        db_path = self.create_database()
        initial_size = db_path.stat().st_size

        success, freed = _clean_sqlite_db(db_path, ["DELETE FROM urls"])

        self.assertTrue(success)
        self.assertEqual(freed, max(0, initial_size - db_path.stat().st_size))
        self.assertEqual(self.row_count(db_path), 0)

    def test_sqlite_cleanup_fails_when_no_query_runs(self):
        db_path = self.create_database()

        success, freed = _clean_sqlite_db(db_path, ["DELETE FROM missing_table"])

        self.assertFalse(success)
        self.assertEqual(freed, 0)

    def test_sqlite_cleanup_honors_exclusion(self):
        db_path = self.create_database()
        config = self.base / "exclusions.json"
        config.write_text(json.dumps({"exclude": [str(db_path)]}), encoding="utf-8")
        load_exclusions(str(config))

        success, freed = _clean_sqlite_db(db_path, ["DELETE FROM urls"])

        self.assertFalse(success)
        self.assertEqual(freed, 0)
        self.assertEqual(self.row_count(db_path), 500)


class BrowserProfileTests(unittest.TestCase):
    def test_chromium_cache_paths_cover_all_profiles_and_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "User Data"
            expected = [
                base / "Default" / "Cache",
                base / "Profile 1" / "Cache",
                base / "ShaderCache",
            ]
            for target in expected:
                target.mkdir(parents=True)
                (target / "cache.bin").write_bytes(b"cache")

            with patch(
                "footprint.browser._browser_targets",
                return_value=[("Test Chromium", base, _CHROMIUM_CACHE_DIRS)],
            ):
                results = clean_browser_data(dry_run=True)

        result_paths = {Path(item["path"]) for item in results}
        self.assertTrue(set(expected).issubset(result_paths))


class OutputAndCommandTests(unittest.TestCase):
    def test_html_report_escapes_dynamic_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "report.html"
            payload = "<script>alert('x')</script>"
            export_to_html(
                {
                    "osint_email": {
                        "target": payload,
                        "results": [
                            {"service": payload, "found": False, "detail": payload}
                        ],
                    }
                },
                str(output),
            )
            report = output.read_text(encoding="utf-8")

        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)

    def test_windows_scheduled_command_quotes_executable(self):
        fake_python = r"C:\Program Files\Python\python.exe"
        with (
            patch("utils.scheduler.platform.system", return_value="Windows"),
            patch("utils.scheduler.sys.executable", fake_python),
            patch("utils.scheduler.subprocess.run") as run,
        ):
            schedule_task("daily")

        command = run.call_args.args[0]
        task_command = command[command.index("/tr") + 1]
        self.assertIn(f'"{fake_python}"', task_command)
        self.assertIn("--clean-all", task_command)

    def test_linux_cron_command_quotes_executable(self):
        fake_python = "/opt/Python Runtime/python"
        current = subprocess.CompletedProcess(["crontab", "-l"], 0, stdout="")
        installed = subprocess.CompletedProcess(["crontab", "-"], 0, stdout="")
        with (
            patch("utils.scheduler.platform.system", return_value="Linux"),
            patch("utils.scheduler.sys.executable", fake_python),
            patch("utils.scheduler.subprocess.run", side_effect=[current, installed]) as run,
        ):
            schedule_task("weekly")

        cron_input = run.call_args_list[1].kwargs["input"]
        self.assertIn("'/opt/Python Runtime/python'", cron_input)
        self.assertIn("# digitalayakizi-cleaner", cron_input)

    def test_positive_int_rejects_zero(self):
        self.assertEqual(positive_int("3"), 3)
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")


if __name__ == "__main__":
    unittest.main()
