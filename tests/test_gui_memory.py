import queue
import threading
import unittest
from unittest.mock import Mock, call, patch

from gui import TERMINAL_MAX_LINES, TERMINAL_RETAIN_LINES, TrackherApp


class GuiMemoryTests(unittest.TestCase):
    @staticmethod
    def fake_asyncio_run(result):
        def runner(coro):
            coro.close()
            return result

        return runner

    def make_app(self) -> TrackherApp:
        app = object.__new__(TrackherApp)
        app._ui_queue = queue.Queue()
        app._ui_state_lock = threading.Lock()
        app._closing = threading.Event()
        app._queue_after_id = None
        app._terminal_line_count = 0
        app.terminal = Mock()
        app.chk_history = Mock()
        app.chk_history.get.return_value = 0
        app.profile_var = Mock()
        app.profile_var.get.return_value = "standard"
        app.health_live_var = Mock()
        app.health_live_var.get.return_value = 0
        app.osint_entry = Mock()
        app.lbl_health_summary = Mock()
        app.btn_health = Mock()
        return app

    def test_terminal_history_is_trimmed_in_chunks(self):
        app = self.make_app()
        app._terminal_line_count = TERMINAL_MAX_LINES

        app._append_terminal("new line")

        lines_deleted = TERMINAL_MAX_LINES + 1 - TERMINAL_RETAIN_LINES
        app.terminal.delete.assert_called_once_with(
            "1.0",
            f"{lines_deleted + 1}.0",
        )
        self.assertEqual(app._terminal_line_count, TERMINAL_RETAIN_LINES)
        self.assertEqual(
            app.terminal.configure.call_args_list,
            [call(state="normal"), call(state="disabled")],
        )

    def test_multiline_terminal_output_updates_line_count(self):
        app = self.make_app()

        app._append_terminal("first\nsecond")

        self.assertEqual(app._terminal_line_count, 2)
        app.terminal.delete.assert_not_called()

    def test_close_discards_queue_and_rejects_new_updates(self):
        app = self.make_app()
        app._queue_after_id = "after#1"
        app.after_cancel = Mock()
        app.destroy = Mock()
        app._ui_queue.put((Mock(), (), {}))

        app._on_close()
        app.post_ui(Mock())

        self.assertTrue(app._closing.is_set())
        self.assertTrue(app._ui_queue.empty())
        self.assertEqual(app._ui_queue.unfinished_tasks, 0)
        app.after_cancel.assert_called_once_with("after#1")
        app.destroy.assert_called_once_with()

    def test_drain_balances_queue_tasks(self):
        app = self.make_app()
        callback = Mock()
        app.after = Mock(return_value="after#2")
        app._ui_queue.put((callback, ("value",), {"enabled": True}))

        app._drain_ui_queue()

        callback.assert_called_once_with("value", enabled=True)
        self.assertEqual(app._ui_queue.unfinished_tasks, 0)
        self.assertEqual(app._queue_after_id, "after#2")

    def test_username_scan_reports_unknown_when_no_verified_match(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_user = Mock()
        results = [
            {
                "platform": "Reddit",
                "url": "https://example.test/reddit-user",
                "found": False,
                "status": "unknown",
                "detail": "",
                "unknown_cause": "bot_blocked",
            }
        ]

        with patch("gui.asyncio.run", side_effect=self.fake_asyncio_run(results)):
            app.do_username_osint("reddit-user")

        printed = [args[0] for args, _kwargs in app.print_to_terminal.call_args_list]
        self.assertIn("  [-] No verified username matches were found.", printed)
        self.assertTrue(
            any(
                "Could not verify 1 platforms (bot blocked 1): Reddit" in line
                for line in printed
            )
        )
        self.assertTrue(any("Digital Footprint Risk Score" in line for line in printed))
        self.assertTrue(any("SCAN DIFF" in line for line in printed))
        app.post_ui.assert_called_once_with(app.btn_user.configure, state="normal")

    def test_username_scan_warns_when_result_list_is_empty(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_user = Mock()

        with patch("gui.asyncio.run", side_effect=self.fake_asyncio_run([])):
            app.do_username_osint("empty-user")

        app.print_to_terminal.assert_called_once_with(
            "  [!] WARNING: Username scan returned no platform results."
        )
        app.post_ui.assert_called_once_with(app.btn_user.configure, state="normal")

    def test_username_scan_includes_remediation_actions(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_user = Mock()
        results = [
            {
                "platform": "GitHub",
                "url": "https://github.com/octocat",
                "found": True,
                "status": "found",
                "detail": "",
                "public_metadata": {
                    "username": "octocat",
                    "display_name": "Octo Cat",
                    "website": "octo.example",
                },
            },
            {
                "platform": "GitLab",
                "url": "https://gitlab.com/octocat",
                "found": True,
                "status": "found",
                "detail": "",
                "public_metadata": {
                    "username": "octocat",
                    "display_name": "Octo Cat",
                    "website": "https://octo.example/about",
                },
            }
        ]

        with patch("gui.asyncio.run", side_effect=self.fake_asyncio_run(results)):
            app.do_username_osint("octocat")

        printed = [args[0] for args, _kwargs in app.print_to_terminal.call_args_list]
        self.assertTrue(any("Identity Correlation" in line for line in printed))
        self.assertTrue(any("Remediation / Privacy Actions" in line for line in printed))
        self.assertTrue(any("Account Security / 2FA" in line for line in printed))
        self.assertTrue(any("Delete Account / Help" in line for line in printed))

    def test_email_scan_reports_unknown_and_skipped_when_no_verified_match(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_email = Mock()
        results = {
            "accounts": [
                {"service": "GitHub", "found": False, "status": "UNKNOWN", "detail": ""},
                {
                    "service": "Flickr",
                    "found": False,
                    "status": "NOT_CONFIGURED",
                    "detail": "FLICKR_API_KEY not configured",
                },
                {"service": "Netflix", "found": False, "status": "MANUAL", "detail": ""},
            ],
            "breaches": [
                {"service": "Have I Been Pwned", "found": False, "status": "NOT_CONFIGURED", "detail": ""},
            ],
        }

        with patch("gui.asyncio.run", side_effect=self.fake_asyncio_run(results)):
            app.do_email_osint("new@example.test")

        printed = [args[0] for args, _kwargs in app.print_to_terminal.call_args_list]
        self.assertIn("    0 verified accounts discovered automatically.", printed)
        self.assertTrue(any("does not mean the email has no accounts" in line for line in printed))
        self.assertTrue(any("Could not verify 2 services: GitHub, Flickr" in line for line in printed))
        self.assertTrue(any("1 services require manual review." in line for line in printed))
        self.assertTrue(any("Sample: Netflix" in line for line in printed))
        self.assertTrue(any("Have I Been Pwned: NOT CONFIGURED" in line for line in printed))
        self.assertTrue(any("Manual email trace links" in line for line in printed))
        self.assertTrue(any("Digital Footprint Risk Score" in line for line in printed))
        self.assertTrue(any("SCAN DIFF" in line for line in printed))
        app.post_ui.assert_called_once_with(app.btn_email.configure, state="normal")

    def test_email_scan_warns_when_result_list_is_empty(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_email = Mock()

        with patch("gui.asyncio.run", side_effect=self.fake_asyncio_run([])):
            app.do_email_osint("empty@example.test")

        app.print_to_terminal.assert_called_once_with(
            "  [!] WARNING: Email scan returned no service results."
        )
        app.post_ui.assert_called_once_with(app.btn_email.configure, state="normal")

    def test_email_scan_uses_selected_profile_from_gui(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_email = Mock()
        app.osint_entry.get.return_value = "owner@example.test"
        app.profile_var.get.return_value = "quick"

        captured = {}

        async def fake_check_email(target, *, profile="standard"):
            captured["target"] = target
            captured["profile"] = profile
            return {"accounts": [], "breaches": []}

        with patch("gui.check_email", side_effect=fake_check_email):
            app.do_email_osint("owner@example.test", profile=app.profile_var.get())

        self.assertEqual(captured["profile"], "quick")

    def test_username_scan_uses_selected_profile_from_gui(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_user = Mock()
        app.osint_entry.get.return_value = "octocat"
        app.profile_var.get.return_value = "email-only"

        captured = {}

        async def fake_check_username(target, *, profile="standard"):
            captured["target"] = target
            captured["profile"] = profile
            return []

        with patch("gui.check_username_async", side_effect=fake_check_username):
            app.do_username_osint("octocat", profile=app.profile_var.get())

        self.assertEqual(captured["profile"], "email-only")

    def test_platform_health_updates_summary_label(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()

        with patch(
            "gui.run_platform_health_check",
            return_value={
                "counts": {"HEALTHY": 10, "DEGRADED": 2, "BROKEN": 1, "UNKNOWN": 0},
                "items": [],
                "live_enabled": True,
                "cache_hits": 3,
            },
        ):
            app.do_platform_health_check(live=True)

        printed = [args[0] for args, _kwargs in app.print_to_terminal.call_args_list]
        self.assertTrue(any("Healthy: 10 | Degraded: 2 | Broken: 1 | Unknown: 0" in line for line in printed))
        app.post_ui.assert_any_call(
            app.lbl_health_summary.configure,
            text="Platform Health: Healthy: 10 | Degraded: 2 | Broken: 1 | Unknown: 0",
        )
        app.post_ui.assert_any_call(app.btn_health.configure, state="normal")


if __name__ == "__main__":
    unittest.main()
