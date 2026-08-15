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

    def test_email_scan_reports_unknown_and_skipped_when_no_verified_match(self):
        app = self.make_app()
        app.print_to_terminal = Mock()
        app.post_ui = Mock()
        app.btn_email = Mock()
        results = [
            {"service": "GitHub", "found": False, "status": "unknown", "detail": ""},
            {"service": "Netflix", "found": False, "status": "skipped", "detail": ""},
        ]

        with patch("gui.asyncio.run", side_effect=self.fake_asyncio_run(results)):
            app.do_email_osint("new@example.test")

        printed = [args[0] for args, _kwargs in app.print_to_terminal.call_args_list]
        self.assertIn("  [-] No verified email matches were found.", printed)
        self.assertTrue(any("Could not verify 1 services: GitHub" in line for line in printed))
        self.assertTrue(any("Skipped 1 risky services: Netflix" in line for line in printed))
        app.post_ui.assert_called_once_with(app.btn_email.configure, state="normal")

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
            }
        ]

        with patch("gui.asyncio.run", side_effect=self.fake_asyncio_run(results)):
            app.do_username_osint("reddit-user")

        printed = [args[0] for args, _kwargs in app.print_to_terminal.call_args_list]
        self.assertIn("  [-] No verified username matches were found.", printed)
        self.assertTrue(any("Could not verify 1 platforms: Reddit" in line for line in printed))
        app.post_ui.assert_called_once_with(app.btn_user.configure, state="normal")

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


if __name__ == "__main__":
    unittest.main()
