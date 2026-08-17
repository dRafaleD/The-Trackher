import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from main import build_parser
from utils import __version__
from utils import display


class TerminalDisplayTests(unittest.TestCase):
    def capture(self, callback, width: int = 120) -> str:
        buffer = io.StringIO()
        test_console = Console(
            file=buffer,
            force_terminal=False,
            color_system=None,
            width=width,
        )
        with patch.object(display, "console", test_console):
            callback()
        return buffer.getvalue()

    def test_banner_branding_uses_trackher(self):
        output = self.capture(display.show_banner)

        self.assertIn("TRACKHER", output)
        self.assertIn("Digital Footprint & Privacy Toolkit", output)
        self.assertNotIn("Digital Ayak Izi", output)

    def test_home_screen_displays_dynamic_version_and_catalog_counts(self):
        output = self.capture(display.show_home_screen)
        project_root = Path(__file__).resolve().parent.parent
        username_count = len(
            json.loads((project_root / "osint" / "platforms.json").read_text(encoding="utf-8"))
        )
        email_count = len(
            json.loads((project_root / "osint" / "email_platforms.json").read_text(encoding="utf-8"))
        )

        self.assertIn(f"v{__version__}", output)
        self.assertIn(f"{username_count} platforms", output)
        self.assertIn(f"{email_count} services", output)
        self.assertIn("trackher --gui", output)
        self.assertIn("Quick Commands", output)
        self.assertIn("Trackher v", output)
        self.assertIn("trackher@osint ~ $", output)
        self.assertNotIn("Project Identity", output)
        self.assertNotIn("Investigation", output)
        self.assertNotIn("Build", output)

    def test_home_screen_examples_are_valid_current_cli_commands(self):
        parser = build_parser()
        examples = (
            ["--username", "sampleuser"],
            ["--email", "sample@example.com"],
            ["--profile", "deep", "--username", "sampleuser"],
            ["--health-check"],
            ["--gui"],
            ["--help"],
        )

        for argv in examples[:-1]:
            parsed = parser.parse_args(argv)
            self.assertIsNotNone(parsed)

        with self.assertRaises(SystemExit) as raised:
            parser.parse_args(examples[-1])
        self.assertEqual(raised.exception.code, 0)

    def test_home_screen_removes_duplicate_plain_trackher_and_hotkeys(self):
        output = self.capture(display.show_home_screen)

        self.assertEqual(output.count("TRACKHER"), 1)
        self.assertIn("[A] Remediation Actions", output)
        self.assertIn("[G] Optional GUI", output)
        self.assertEqual(output.count("[G]"), 1)
        self.assertNotIn("[G] Remediation Guidance", output)
        self.assertNotIn("[O] Reporting", output)

    def test_home_screen_falls_back_cleanly_on_narrow_terminals(self):
        output = self.capture(display.show_home_screen, width=72)

        self.assertIn("TRACKHER", output)
        self.assertIn("trackher --username <username>", output)
        self.assertIn("trackher --help", output)
        self.assertIn("trackher@osint ~ $", output)
        self.assertNotIn("Investigation", output)
        self.assertNotIn("Build", output)
        self.assertTrue(output.strip())
        self.assertLessEqual(max(len(line) for line in output.splitlines()), 72)


if __name__ == "__main__":
    unittest.main()
