from __future__ import annotations

import threading
import tkinter as tk


TERMINAL_MAX_LINES = 2_000
TERMINAL_RETAIN_LINES = 1_500


class TerminalOutputMixin:
    """Provide the bounded terminal output behavior used by the application."""

    def _append_terminal(self, text: str):
        self.terminal.configure(state="normal")
        try:
            self.terminal.insert(tk.END, text + "\n")
            self._terminal_line_count += text.count("\n") + 1
            if self._terminal_line_count > TERMINAL_MAX_LINES:
                lines_to_delete = self._terminal_line_count - TERMINAL_RETAIN_LINES
                self.terminal.delete("1.0", f"{lines_to_delete + 1}.0")
                self._terminal_line_count -= lines_to_delete
            self.terminal.see(tk.END)
        finally:
            self.terminal.configure(state="disabled")

    def print_to_terminal(self, text: str):
        if threading.current_thread() is threading.main_thread():
            self._append_terminal(text)
        else:
            self.post_ui(self._append_terminal, text)
