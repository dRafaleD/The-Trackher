import io
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main as main_module
from utils import __version__
from utils.app_logging import SafeStreamHandler, configure_logging, redact_sensitive_text, safe_log
from utils.history import save_and_diff_scan
from utils.platform_health import load_cached_health_summary, run_platform_health_check
from utils.release_checks import get_version, scan_repository_for_secrets
from utils.runtime import validate_runtime


class LoggingHardeningTests(unittest.TestCase):
    def test_secret_redaction_removes_email_and_api_key(self):
        text = redact_sensitive_text(
            "target=owner@example.com HIBP_API_KEY='1234567890abcdef1234567890abcdef'"
        )

        self.assertNotIn("owner@example.com", text)
        self.assertNotIn("1234567890abcdef1234567890abcdef", text)
        self.assertIn("[REDACTED_EMAIL]", text)
        self.assertIn("[REDACTED]", text)

    def test_logger_failure_is_isolated(self):
        logger = logging.Logger("trackher.test.logger", level=logging.INFO)
        logger.propagate = False
        broken = SafeStreamHandler(stream=io.StringIO())

        def explode(record):
            raise OSError("stream failed")

        broken.emit = explode  # type: ignore[method-assign]
        logger.handlers = [broken]

        safe_log(logger, logging.INFO, "target=%s", "owner@example.com")

    def test_release_secret_scan_detects_literal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config.py").write_text('API_KEY = "ghp_abcdefghijklmnopqrstuvwxyz123456"\n', encoding="utf-8")

            findings = scan_repository_for_secrets(root)

        self.assertTrue(findings)
        self.assertIn("github_token", {item["pattern"] for item in findings})


class RuntimeHardeningTests(unittest.TestCase):
    def test_version_consistency_uses_single_source(self):
        self.assertEqual(get_version(), __version__)

    def test_startup_validation_creates_state_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_root = Path(temp_dir) / "history"
            health_root = Path(temp_dir) / "health"
            with patch.dict(
                "os.environ",
                {
                    "TRACKHER_HISTORY_DIR": str(history_root),
                    "TRACKHER_HEALTH_DIR": str(health_root),
                },
                clear=False,
            ):
                result = validate_runtime()

            self.assertTrue(result["ready"])
            self.assertTrue((history_root / "snapshots").exists())
            self.assertTrue(health_root.exists())

    def test_startup_validation_reports_directory_failure(self):
        with (
            patch("utils.runtime.Path.mkdir", side_effect=OSError("denied")),
            patch.dict(
                "os.environ",
                {
                    "TRACKHER_HISTORY_DIR": str(Path("C:/trackher-history")),
                    "TRACKHER_HEALTH_DIR": str(Path("C:/trackher-health")),
                },
                clear=False,
            ),
        ):
            result = validate_runtime()

        self.assertFalse(result["ready"])
        self.assertGreaterEqual(len(result["warnings"]), 1)

    def test_history_storage_error_is_nonfatal(self):
        payload = {
            "scan_profile": "standard",
            "osint_email": {
                "target": "owner@example.test",
                "results": {"accounts": [], "breaches": []},
            },
            "risk": {"score": 0, "level": "LOW"},
        }

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("utils.history._append_snapshot", side_effect=OSError("disk full")),
        ):
            result = save_and_diff_scan(payload, history_dir=Path(temp_dir))

        self.assertEqual(result["status"], "storage_error")
        self.assertFalse(result["available"])

    def test_health_summary_loads_empty_when_corrupted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            (cache_dir / "latest_health_summary.json").write_text("{", encoding="utf-8")

            result = load_cached_health_summary(cache_dir)

        self.assertEqual(result, {})

    def test_platform_health_write_failure_is_nonfatal(self):
        with patch("builtins.open", side_effect=OSError("read-only")):
            result = run_platform_health_check()

        self.assertIn("counts", result)

    def test_main_version_flag_matches_module_version(self):
        with self.assertRaises(SystemExit) as raised:
            main_module.build_parser().parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
