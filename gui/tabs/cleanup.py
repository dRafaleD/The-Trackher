from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from footprint.browser import clean_browser_data
from footprint.shell import clean_shell_history
from footprint.shredder import shred_directory, shred_file
from footprint.system import clean_system_traces
from gui.widgets.common import ctk
from utils.helpers import expand_path, format_size


class CleanupTabMixin:
    """Build and operate the existing cleaner and shredder tabs."""

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
        self.run_in_thread(
            self.do_clean,
            dry_run,
            clean_shell,
            clean_browser,
            clean_system,
        )

    def do_clean(self, dry_run: bool, clean_shell: bool, clean_browser: bool, clean_system: bool):
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
