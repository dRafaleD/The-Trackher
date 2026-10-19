from __future__ import annotations

import threading
import tkinter as tk


TERMINAL_MAX_LINES = 2_000
TERMINAL_RETAIN_LINES = 1_500
TERMINAL_COLORS = {
    'body': '#c5cfdb',
    'muted': '#91a4ba',
    'heading': '#aebfff',
    'info': '#69c9df',
    'success': '#78cfad',
    'warning': '#e6bc7b',
    'error': '#ee929c',
}


def terminal_category(line: str) -> str:
    """Style output markers, not arbitrary words inside usernames or URLs."""
    text = line.strip().casefold()
    if text.startswith(('[-] error:', '[-] ui error:', '[-] failed:', '[error]')):
        return 'error'
    if text.startswith(('[+] found:', '[+] success:', '[ok]', '[healthy]')):
        return 'success'
    if text.startswith(('[-] not found:', '[-] no verified', '[-] no ', '[manual]')):
        return 'muted'
    if text.startswith(('[?]', '[~]', '[paused]', '[warning]', '[broken]', '[degraded]', '[unknown]', '[!]', '! ', '[+0', '[+1', '[+2', '[+3', '[+4', '[+5', '[+6', '[+7', '[+8', '[+9')):
        return 'info' if text.startswith(('[!] total ', '[!] finished:')) else 'warning'
    if text in {
        'verified accounts', 'possible accounts', 'checked and not found',
        'manual investigation', 'breaches', 'identity correlation',
        'remediation / privacy actions', 'digital footprint risk score', 'scan diff',
    }:
        return 'heading'
    if text.startswith('[i] runtime warning:'):
        return 'warning'
    if text.startswith(('[i]', '[+]', '->', 'root@trackher:')):
        return 'info'
    return 'body'


class TerminalOutputMixin:
    """Provide the bounded terminal output behavior used by the application."""

    def _append_terminal(self, text: str):
        self.terminal.configure(state="normal")
        try:
            for line in (text + "\n").splitlines(keepends=True):
                self.terminal.insert(tk.END, line, (terminal_category(line),))
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
