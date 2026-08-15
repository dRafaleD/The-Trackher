from __future__ import annotations

import asyncio
import platform
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from PIL import Image

try:
    import customtkinter as ctk
except ImportError as exc:
    raise ImportError(
        "customtkinter eksik; 'pip install -r requirements.txt' calistirin"
    ) from exc

from footprint.browser import clean_browser_data
from footprint.shell import clean_shell_history
from footprint.shredder import shred_directory, shred_file
from footprint.system import clean_system_traces
from osint.checker import check_email
from osint.dorking import generate_dorks
from osint.services import ALL_SERVICES, PASSIVE_SERVICES
from osint.username_checker import USERNAME_PLATFORMS, check_username_async
from utils.helpers import expand_path, format_size, is_valid_email, is_valid_username_query


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

TERMINAL_MAX_LINES = 2_000
TERMINAL_RETAIN_LINES = 1_500


def _format_result_sample(items: list[dict], key: str, limit: int = 5) -> str:
    """Build a short, deduplicated sample string from result rows."""
    labels: list[str] = []
    for item in items:
        value = str(item.get(key, "")).strip()
        if not value or value in labels:
            continue
        labels.append(value)
        if len(labels) >= limit:
            break

    if not labels:
        return ""
    suffix = " ..." if len(items) > len(labels) else ""
    return ", ".join(labels) + suffix


class TrackherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._ui_queue = queue.Queue()
        self._ui_state_lock = threading.Lock()
        self._closing = threading.Event()
        self._queue_after_id = None
        self._terminal_line_count = 0

        self.title("Trackher - OSINT and Digital Footprint Cleaner")
        self.geometry("900x700")
        self.minsize(800, 650)

        self.bg_color = "#0c0c0c"
        self.fg_color = "#00ff00"
        font_map = {
            "Windows": ("Consolas", "Segoe UI"),
            "Darwin": ("Menlo", "Helvetica Neue"),
            "Linux": ("DejaVu Sans Mono", "DejaVu Sans"),
        }
        terminal_font, ui_font = font_map.get(platform.system(), ("Courier", "Helvetica"))
        self.font_terminal = ctk.CTkFont(family=terminal_font, size=13)
        self.font_ui = ctk.CTkFont(family=ui_font, size=13, weight="bold")

        self.configure(fg_color="#181818")

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=(15, 5))

        logo_path = Path(__file__).parent / "assets" / "logo.jpg"
        if logo_path.exists():
            with Image.open(logo_path) as source_image:
                image = source_image.copy()
            self.logo_image = ctk.CTkImage(light_image=image, dark_image=image, size=(40, 40))
            self.lbl_logo = ctk.CTkLabel(self.header_frame, image=self.logo_image, text="")
            self.lbl_logo.pack(side="left", padx=(0, 10))

        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="TRACKHER",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#00d2ff",
        )
        self.lbl_title.pack(side="left")

        self.tabview = ctk.CTkTabview(
            self,
            width=860,
            height=200,
            fg_color="#242424",
            segmented_button_fg_color="#333333",
        )
        self.tabview.pack(padx=20, pady=5, fill="x")

        self.tabview.add("OSINT")
        self.tabview.add("Cleaner")
        self.tabview.add("Shredder")

        self.setup_osint_tab()
        self.setup_cleaning_tab()
        self.setup_shredder_tab()

        self.lbl_term = ctk.CTkLabel(self, text="Terminal Output:", font=self.font_ui)
        self.lbl_term.pack(anchor="w", padx=20, pady=(10, 0))

        self.terminal = ctk.CTkTextbox(
            self,
            width=860,
            height=300,
            fg_color=self.bg_color,
            text_color=self.fg_color,
            font=self.font_terminal,
            wrap="word",
            border_width=2,
            border_color="#333",
            state="disabled",
        )
        self.terminal.pack(padx=20, pady=(0, 20), fill="both", expand=True)

        self.print_to_terminal("root@trackher:~# System initialized.")
        self.print_to_terminal("root@trackher:~# Modules loaded. Awaiting instructions...\n")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_ui_drain()

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

    def setup_osint_tab(self):
        tab = self.tabview.tab("OSINT")

        self.osint_entry = ctk.CTkEntry(
            tab,
            placeholder_text="Enter target email or username...",
            width=350,
            font=self.font_ui,
        )
        self.osint_entry.grid(row=0, column=0, padx=20, pady=30)

        self.btn_email = ctk.CTkButton(
            tab,
            text="Scan Email",
            font=self.font_ui,
            command=self.start_email_osint,
            fg_color="#1f538d",
            hover_color="#14375d",
        )
        self.btn_email.grid(row=0, column=1, padx=10, pady=30)

        self.btn_user = ctk.CTkButton(
            tab,
            text="Scan Username",
            font=self.font_ui,
            command=self.start_username_osint,
            fg_color="#1f538d",
            hover_color="#14375d",
        )
        self.btn_user.grid(row=0, column=2, padx=10, pady=30)

        self.btn_dork = ctk.CTkButton(
            tab,
            text="Generate Dorks",
            font=self.font_ui,
            command=self.do_dork,
            fg_color="#0d7a5f",
            hover_color="#095746",
        )
        self.btn_dork.grid(row=0, column=3, padx=10, pady=30)

    def start_email_osint(self):
        target = self.osint_entry.get().strip()
        if not target:
            return
        if not is_valid_email(target):
            self.print_to_terminal("  [-] ERROR: Invalid email address.")
            return
        self.btn_email.configure(state="disabled")
        self.print_to_terminal(f"\n[+] OSINT: Initiating email recon for '{target}'...")
        self.print_to_terminal(
            f"  -> Email catalog: {len(ALL_SERVICES)} services; "
            f"{len(PASSIVE_SERVICES)} passive checks, "
            f"{len(ALL_SERVICES) - len(PASSIVE_SERVICES)} side-effectful checks skipped."
        )
        self.run_in_thread(self.do_email_osint, target)

    def do_email_osint(self, target: str):
        try:
            results = asyncio.run(check_email(target))
            if not results:
                self.print_to_terminal("  [!] WARNING: Email scan returned no service results.")
                return

            found = [result for result in results if result["found"]]
            unknown = [result for result in results if result.get("status") == "unknown"]
            skipped = [result for result in results if result.get("status") == "skipped"]
            unknown_count = len(unknown)
            skipped_count = len(skipped)

            for result in found:
                detail = f" - {result.get('detail', '')}" if result.get("detail") else ""
                self.print_to_terminal(f"  [+] FOUND: {result['service']}{detail}")

            if not found:
                self.print_to_terminal("  [-] No verified email matches were found.")

            if unknown:
                sample = _format_result_sample(unknown, "service")
                self.print_to_terminal(
                    f"  [?] Could not verify {unknown_count} services"
                    f"{': ' + sample if sample else '.'}"
                )

            if skipped:
                sample = _format_result_sample(skipped, "service")
                self.print_to_terminal(
                    f"  [~] Skipped {skipped_count} risky services"
                    f"{': ' + sample if sample else '.'}"
                )

            self.print_to_terminal(
                f"[!] Total {len(found)} verified matches. "
                f"(Catalog {len(results)}, {unknown_count} unknown, "
                f"{skipped_count} safely skipped)"
            )
        finally:
            self.post_ui(self.btn_email.configure, state="normal")

    def start_username_osint(self):
        target = self.osint_entry.get().strip()
        if not is_valid_username_query(target):
            self.print_to_terminal("  [-] ERROR: Username must be 1-100 printable characters.")
            return
        self.btn_user.configure(state="disabled")
        self.print_to_terminal(f"\n[+] OSINT: Initiating username recon for '{target}'...")
        self.print_to_terminal(
            f"  -> Username platform pool: {len(USERNAME_PLATFORMS)} platforms."
        )
        self.run_in_thread(self.do_username_osint, target)

    def do_username_osint(self, target: str):
        try:
            results = asyncio.run(check_username_async(target))
            if not results:
                self.print_to_terminal("  [!] WARNING: Username scan returned no platform results.")
                return

            found = [result for result in results if result["found"]]
            unknown = [result for result in results if result.get("status") == "unknown"]
            unknown_count = len(unknown)

            for result in found:
                self.print_to_terminal(f"  [+] FOUND: {result['platform']} -> {result['url']}")

            if not found:
                self.print_to_terminal("  [-] No verified username matches were found.")

            if unknown:
                sample = _format_result_sample(unknown, "platform")
                self.print_to_terminal(
                    f"  [?] Could not verify {unknown_count} platforms"
                    f"{': ' + sample if sample else '.'}"
                )

            self.print_to_terminal(
                f"[!] Total {len(found)} verified matches. "
                f"(Scanned {len(results)}, {unknown_count} could not be verified)"
            )
        finally:
            self.post_ui(self.btn_user.configure, state="normal")

    def do_dork(self):
        target = self.osint_entry.get().strip()
        if not target:
            return
        self.print_to_terminal(f"\n[+] DORK: Generating search links for '{target}'...")

        for dork in generate_dorks(target):
            self.print_to_terminal(f"  [{dork['engine']}] {dork['type']}: {dork['url']}")

    def setup_cleaning_tab(self):
        tab = self.tabview.tab("Cleaner")

        self.chk_shell = ctk.CTkCheckBox(tab, text="Shell History and Logs", font=self.font_ui)
        self.chk_shell.grid(row=0, column=0, padx=30, pady=15, sticky="w")
        self.chk_shell.select()

        self.chk_browser = ctk.CTkCheckBox(
            tab,
            text="Browser Cache and Cookies (SQLite Mode)",
            font=self.font_ui,
        )
        self.chk_browser.grid(row=1, column=0, padx=30, pady=15, sticky="w")
        self.chk_browser.select()

        self.chk_system = ctk.CTkCheckBox(
            tab,
            text="System Traces (Temp, Trash, Thumbnails)",
            font=self.font_ui,
        )
        self.chk_system.grid(row=2, column=0, padx=30, pady=15, sticky="w")
        self.chk_system.select()

        self.chk_dryrun = ctk.CTkSwitch(
            tab,
            text="SIMULATION (Dry-Run)",
            progress_color="#d35400",
            font=self.font_ui,
        )
        self.chk_dryrun.grid(row=0, column=1, rowspan=2, padx=100, pady=10)
        self.chk_dryrun.select()

        self.btn_clean = ctk.CTkButton(
            tab,
            text="START CLEANING",
            font=self.font_ui,
            command=self.start_clean,
            fg_color="#c0392b",
            hover_color="#922b21",
            width=200,
            height=40,
        )
        self.btn_clean.grid(row=2, column=1, padx=100, pady=10)

    def start_clean(self):
        dry_run = bool(self.chk_dryrun.get())
        clean_shell = bool(self.chk_shell.get())
        clean_browser = bool(self.chk_browser.get())
        clean_system = bool(self.chk_system.get())
        if not any((clean_shell, clean_browser, clean_system)):
            self.print_to_terminal("  [-] ERROR: Select at least one cleaning module.")
            return
        if not dry_run and not messagebox.askyesno(
            "Confirm destructive cleanup",
            "Selected traces will be permanently deleted. Continue?",
            parent=self,
        ):
            return

        mode = "SIMULATION" if dry_run else "DESTRUCTIVE MODE"
        self.btn_clean.configure(state="disabled")
        self.print_to_terminal(f"\n[+] INIT CLEANING SEQUENCE [{mode}]...")
        self.run_in_thread(self.do_clean, dry_run, clean_shell, clean_browser, clean_system)

    def do_clean(
        self,
        dry_run: bool,
        clean_shell: bool,
        clean_browser: bool,
        clean_system: bool,
    ):
        try:
            all_items: list[dict] = []
            if clean_shell:
                self.print_to_terminal("  -> Purging shell traces...")
                all_items.extend(clean_shell_history(dry_run=dry_run))

            if clean_browser:
                self.print_to_terminal("  -> Wiping browser data...")
                all_items.extend(clean_browser_data(dry_run=dry_run))

            if clean_system:
                self.print_to_terminal("  -> Cleaning system temporary files...")
                all_items.extend(clean_system_traces(dry_run=dry_run))

            total_size = sum(item.get("size", 0) for item in all_items)

            show_max = 20
            for item in all_items[:show_max]:
                self.print_to_terminal(
                    f"    - {item['type']} | {item['path']} ({format_size(item['size'])})"
                )
            if len(all_items) > show_max:
                self.print_to_terminal(f"    ... and {len(all_items) - show_max} more items.")

            action = "identified" if dry_run else "processed"
            size_label = "Potential space" if dry_run else "Reclaimed space"
            self.print_to_terminal(
                f"[!] FINISHED: Total {len(all_items)} items {action}. "
                f"{size_label}: {format_size(total_size)}"
            )
        finally:
            self.post_ui(self.btn_clean.configure, state="normal")

    def setup_shredder_tab(self):
        tab = self.tabview.tab("Shredder")

        label = ctk.CTkLabel(
            tab,
            text="WARNING: Permanent overwrite is best-effort and cannot be undone.",
            text_color="#e74c3c",
            font=self.font_ui,
        )
        label.grid(row=0, column=0, columnspan=2, pady=(15, 5))

        self.shred_path = ctk.CTkEntry(
            tab,
            placeholder_text="Absolute path to file or directory...",
            width=500,
            font=self.font_ui,
        )
        self.shred_path.grid(row=1, column=0, padx=20, pady=20)

        self.btn_shred = ctk.CTkButton(
            tab,
            text="SHRED TARGET",
            font=self.font_ui,
            command=self.start_shred,
            fg_color="#8b0000",
            hover_color="#5a0000",
            width=150,
        )
        self.btn_shred.grid(row=1, column=1, padx=10, pady=20)

    def start_shred(self):
        path_str = self.shred_path.get().strip()
        if not path_str:
            return

        try:
            target = expand_path(path_str, resolve_symlinks=False)
        except (OSError, ValueError):
            self.print_to_terminal("  [-] ERROR: Invalid path format.")
            return

        if not target.exists():
            self.print_to_terminal("  [-] ERROR: Target path not found.")
            return
        if not messagebox.askyesno(
            "Confirm secure wipe",
            "This operation cannot be undone. SSD/COW storage may retain copies:\n\n"
            f"{target}\n\nContinue?",
            parent=self,
        ):
            return

        self.btn_shred.configure(state="disabled")
        self.print_to_terminal(f"\n[+] SHRED: Attempting secure wipe on '{target}'...")
        self.run_in_thread(self.do_shred, target)

    def do_shred(self, target: Path):
        success = False
        try:
            if target.is_file():
                success = shred_file(str(target), passes=3, dry_run=False)
                message = "  [+] SUCCESS: File securely eradicated."
            elif target.is_dir():
                shredded_count = 0

                def count_shredded(_item):
                    nonlocal shredded_count
                    shredded_count += 1

                shred_directory(
                    str(target),
                    passes=3,
                    dry_run=False,
                    collect_results=False,
                    result_callback=count_shredded,
                )
                success = shredded_count > 0 or not target.exists()
                message = f"  [+] SUCCESS: Directory contents wiped ({shredded_count} items)."
            else:
                message = "  [-] ERROR: Unsupported target type."

            if success:
                self.print_to_terminal(message)
                self.post_ui(self.shred_path.delete, 0, tk.END)
            else:
                self.print_to_terminal("  [-] ERROR: Target could not be securely wiped.")
        finally:
            self.post_ui(self.btn_shred.configure, state="normal")


if __name__ == "__main__":
    app = TrackherApp()
    app.mainloop()
