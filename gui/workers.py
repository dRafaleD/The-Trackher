from __future__ import annotations

import queue
import threading
import tkinter as tk


class UiWorkerMixin:
    """Keep background work and Tk main-thread updates safely separated."""

    def _schedule_ui_drain(self):
        if self._closing.is_set():
            return
        try:
            self._queue_after_id = self.after(50, self._drain_ui_queue)
        except tk.TclError:
            self._queue_after_id = None

    def _drain_ui_queue(self):
        """Run queued GUI updates on the main thread."""
        self._queue_after_id = None
        if self._closing.is_set():
            return

        try:
            while True:
                callback, args, kwargs = self._ui_queue.get_nowait()
                try:
                    callback(*args, **kwargs)
                finally:
                    self._ui_queue.task_done()
        except queue.Empty:
            pass
        except (RuntimeError, tk.TclError):
            return
        except Exception as exc:
            self._append_terminal(f"  [-] UI ERROR: {exc}")

        self._schedule_ui_drain()

    def post_ui(self, callback, *args, **kwargs):
        with self._ui_state_lock:
            if self._closing.is_set():
                return
            self._ui_queue.put_nowait((callback, args, kwargs))

    def _discard_pending_ui_updates(self):
        while True:
            try:
                self._ui_queue.get_nowait()
                self._ui_queue.task_done()
            except queue.Empty:
                return

    def _on_close(self):
        with self._ui_state_lock:
            if self._closing.is_set():
                return
            self._closing.set()
            self._discard_pending_ui_updates()

        after_id = self._queue_after_id
        self._queue_after_id = None
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self.destroy()

    def run_in_thread(self, func, *args):
        if self._closing.is_set():
            return

        def runner():
            try:
                func(*args)
            except Exception as exc:
                self.print_to_terminal(f"  [-] ERROR: {exc}")

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
