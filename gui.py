from __future__ import annotations

import asyncio
import logging
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
from osint.services import ACCOUNT_PLATFORMS, BREACH_PLATFORMS
from osint.username_checker import USERNAME_PLATFORMS, check_username_async
from utils.app_logging import configure_logging, get_logger, safe_log
from utils.app_paths import resource_path
from utils.correlation import build_identity_correlation
from utils.history import clear_scan_history, save_and_diff_scan
from utils.helpers import expand_path, format_size, is_valid_email, is_valid_username_query
from utils.risk import compute_risk
from utils.remediation import build_remediation_report
from utils.profiles import (
    DEFAULT_SCAN_PROFILE,
    PROFILE_ORDER,
    normalize_scan_profile,
    profile_allows_email,
    profile_allows_username,
    profile_description,
    select_email_platforms,
    select_username_platforms,
)
from utils.platform_health import load_cached_health_summary, run_platform_health_check
from utils.runtime import validate_runtime


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

TERMINAL_MAX_LINES = 2_000
TERMINAL_RETAIN_LINES = 1_500
LOGGER = get_logger("gui")


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
        configure_logging()
        super().__init__()
        self._ui_queue = queue.Queue()
        self._ui_state_lock = threading.Lock()
        self._closing = threading.Event()
        self._queue_after_id = None
        self._terminal_line_count = 0
        self.profile_var = tk.StringVar(value=DEFAULT_SCAN_PROFILE)
        self.health_live_var = tk.IntVar(value=0)

        self.title("Trackher - Digital Footprint & Privacy Toolkit")
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

        logo_path = resource_path("assets", "logo.jpg")
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
        runtime_state = validate_runtime()
        for warning in runtime_state.get("warnings", []):
            self.print_to_terminal(f"  [i] Runtime warning: {warning}")
        if runtime_state.get("warnings"):
            safe_log(LOGGER, logging.WARNING, "GUI runtime validation warnings: %s", runtime_state.get("warnings"))
        self._refresh_cached_health_summary()
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

    def _print_remediation_actions(self, remediation: dict):
        if not remediation or not remediation.get("available"):
            return

        self.print_to_terminal("  Remediation / Privacy Actions")
        self.print_to_terminal(
            f"    {remediation.get('item_count', 0)} findings include "
            f"{remediation.get('action_count', 0)} official action links."
        )
        for item in remediation.get("items", []):
            self.print_to_terminal(
                f"    {item.get('platform', 'Unknown')} — {item.get('status', 'FOUND')}"
            )
            for action in item.get("actions", []):
                self.print_to_terminal(
                    f"      • {action.get('label', 'Action')}: {action.get('url', '')}"
                )

    def _print_correlation_summary(self, correlation: dict):
        if not correlation or not correlation.get("available"):
            return

        self.print_to_terminal("  Identity Correlation")
        self.print_to_terminal(
            f"    {correlation.get('count', 0)} likely cross-platform identity links."
        )
        for item in correlation.get("items", []):
            self.print_to_terminal(
                f"    {item.get('confidence', 'LOW')} {item.get('summary', 'Unknown pair')} "
                f"({item.get('confidence_score', 0)}/100)"
            )
            for evidence in item.get("evidence", []):
                marker = "✓" if evidence.get("strength") in {"strong", "medium"} else "~"
                label = evidence.get("label", "signal")
                value = evidence.get("value", "")
                suffix = f": {value}" if value else ""
                self.print_to_terminal(f"      {marker} {label}{suffix}")
            for penalty in item.get("penalties", []):
                self.print_to_terminal(f"      ! {penalty.get('label', 'penalty')}")
        self.print_to_terminal(f"    {correlation.get('disclaimer', '')}")

    def _selected_profile(self) -> str:
        try:
            return normalize_scan_profile(self.profile_var.get())
        except Exception:
            return DEFAULT_SCAN_PROFILE

    def _refresh_cached_health_summary(self):
        summary = load_cached_health_summary()
        if not hasattr(self, "lbl_health_summary"):
            return
        if summary:
            text = summary.get("summary", "Platform Health: cached")
            checked_at = str(summary.get("checked_at", ""))
            suffix = f" | {checked_at}" if checked_at else ""
            self.lbl_health_summary.configure(text=f"Platform Health: {text}{suffix}")
        else:
            self.lbl_health_summary.configure(text="Platform Health: not checked yet")

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

        self.chk_history = ctk.CTkCheckBox(
            tab,
            text="Save Local Scan History",
            font=self.font_ui,
        )
        self.chk_history.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")
        self.chk_history.select()

        self.lbl_profile = ctk.CTkLabel(tab, text="Scan Profile", font=self.font_ui)
        self.lbl_profile.grid(row=1, column=2, padx=(20, 8), pady=(0, 20), sticky="e")

        self.opt_profile = ctk.CTkOptionMenu(
            tab,
            values=list(PROFILE_ORDER),
            variable=self.profile_var,
            width=150,
        )
        self.opt_profile.grid(row=1, column=3, padx=(0, 20), pady=(0, 20), sticky="w")

        self.btn_clear_history = ctk.CTkButton(
            tab,
            text="Clear History",
            font=self.font_ui,
            command=self.clear_local_history,
            fg_color="#7a2f2f",
            hover_color="#5d2222",
        )
        self.btn_clear_history.grid(row=1, column=1, padx=10, pady=(0, 20), sticky="w")

        self.lbl_health_summary = ctk.CTkLabel(
            tab,
            text="Platform Health: not checked yet",
            font=ctk.CTkFont(size=12),
            text_color="#8fbcd4",
        )
        self.lbl_health_summary.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 16), sticky="w")

        self.chk_health_live = ctk.CTkSwitch(
            tab,
            text="Live Health",
            variable=self.health_live_var,
            font=self.font_ui,
        )
        self.chk_health_live.grid(row=2, column=2, padx=(20, 8), pady=(0, 16), sticky="e")

        self.btn_health = ctk.CTkButton(
            tab,
            text="Platform Health",
            font=self.font_ui,
            command=self.start_platform_health_check,
            fg_color="#6c4ad1",
            hover_color="#5234a6",
        )
        self.btn_health.grid(row=2, column=3, padx=(0, 20), pady=(0, 16), sticky="w")

    def clear_local_history(self):
        if not messagebox.askyesno(
            "Clear local scan history",
            "Stored local snapshots will be removed. Continue?",
            parent=self,
        ):
            return

        try:
            result = clear_scan_history()
        except OSError as exc:
            self.print_to_terminal(f"  [-] ERROR: Could not clear local history: {exc}")
            return

        self.print_to_terminal(
            f"  [i] Local scan history cleared. Removed {result['removed_files']} stored entries."
        )

    def start_platform_health_check(self):
        live = bool(self.health_live_var.get())
        self.btn_health.configure(state="disabled")
        mode = "offline schema" if not live else "offline schema + live probes"
        self.print_to_terminal(f"\n[+] HEALTH: Checking platform health in {mode} mode...")
        self.run_in_thread(self.do_platform_health_check, live)

    def do_platform_health_check(self, live: bool = False):
        try:
            result = run_platform_health_check(live=live)
            counts = result.get("counts", {})
            summary = (
                f"Healthy: {counts.get('HEALTHY', 0)} | "
                f"Degraded: {counts.get('DEGRADED', 0)} | "
                f"Broken: {counts.get('BROKEN', 0)} | "
                f"Unknown: {counts.get('UNKNOWN', 0)}"
            )
            self.print_to_terminal(f"  {summary}")
            if result.get("live_enabled"):
                self.print_to_terminal(
                    f"  [i] Live health cache hits: {result.get('cache_hits', 0)}"
                )
            problematic = [
                item for item in result.get("items", [])
                if item.get("state") in {"DEGRADED", "BROKEN", "UNKNOWN"}
            ]
            for item in problematic[:8]:
                self.print_to_terminal(
                    f"  [{item.get('state')}] {item.get('scope')} / "
                    f"{item.get('platform')} ({item.get('detector')}): {item.get('detail')}"
                )
            self.post_ui(
                self.lbl_health_summary.configure,
                text=f"Platform Health: {summary}",
            )
        finally:
            self.post_ui(self.btn_health.configure, state="normal")

    def start_email_osint(self):
        target = self.osint_entry.get().strip()
        if not target:
            return
        if not is_valid_email(target):
            self.print_to_terminal("  [-] ERROR: Invalid email address.")
            return
        profile = self._selected_profile()
        if not profile_allows_email(profile):
            self.print_to_terminal("  [!] Selected profile does not allow email scans.")
            return
        self.btn_email.configure(state="disabled")
        self.print_to_terminal(
            f"\n[+] OSINT: Initiating email recon for '{target}' using profile '{profile}'"
            f" - {profile_description(profile)}..."
        )
        account_platforms, breach_platforms = select_email_platforms(
            profile,
            ACCOUNT_PLATFORMS,
            BREACH_PLATFORMS,
        )
        self.print_to_terminal(
            f"  -> Email catalog: {len(account_platforms)} account services; "
            f"{sum(1 for item in account_platforms if item.get('check', 'manual') != 'manual')} "
            f"side-effect-free automatic detectors; "
            f"{len(breach_platforms)} breach providers; "
            f"{len(ACCOUNT_PLATFORMS) - len(account_platforms)} account services excluded."
        )
        self.run_in_thread(self.do_email_osint, target, profile)

    def do_email_osint(self, target: str, profile: str = DEFAULT_SCAN_PROFILE):
        try:
            results = asyncio.run(check_email(target, profile=profile))
            if not results:
                self.print_to_terminal("  [!] WARNING: Email scan returned no service results.")
                return

            accounts = results.get("accounts", []) if isinstance(results, dict) else results
            breaches = results.get("breaches", []) if isinstance(results, dict) else []
            found = [result for result in accounts if result.get("status") == "FOUND"]
            possible = [result for result in accounts if result.get("status") == "POSSIBLE"]
            not_found = [result for result in accounts if result.get("status") == "NOT_FOUND"]
            manual = [result for result in accounts if result.get("status") == "MANUAL"]
            unknown = [
                result for result in accounts
                if result.get("status") in {"UNKNOWN", "ERROR"}
            ]

            self.print_to_terminal("  Verified Accounts")
            for result in found:
                detail = f" - {result.get('detail', '')}" if result.get("detail") else ""
                self.print_to_terminal(f"  [+] FOUND: {result['service']}{detail}")

            if not found:
                self.print_to_terminal("    0 verified accounts discovered automatically.")
                self.print_to_terminal(
                    "    This does not mean the email has no accounts on other services."
                )

            self.print_to_terminal("  Possible Accounts")
            if possible:
                for result in possible:
                    detail = f" - {result.get('detail', '')}" if result.get("detail") else ""
                    self.print_to_terminal(f"  [~] POSSIBLE: {result['service']}{detail}")
            else:
                self.print_to_terminal("    No possible heuristic matches.")

            if not_found:
                self.print_to_terminal("  Checked and Not Found")
                for result in not_found:
                    detail = f" - {result.get('detail', '')}" if result.get("detail") else ""
                    self.print_to_terminal(f"  [-] NOT FOUND: {result['service']}{detail}")

            if unknown:
                sample = _format_result_sample(unknown, "service")
                self.print_to_terminal(
                    f"  [?] Could not verify {len(unknown)} services"
                    f"{': ' + sample if sample else '.'}"
                )

            self.print_to_terminal("  Manual Investigation")
            if manual:
                self.print_to_terminal(f"    {len(manual)} services require manual review.")
                sample = _format_result_sample(manual, "service")
                if sample:
                    self.print_to_terminal(f"    Sample: {sample}")
            else:
                self.print_to_terminal("    No manual services in catalog.")

            self.print_to_terminal("  Breaches")
            for result in breaches:
                if result.get("status") == "FOUND":
                    self.print_to_terminal(
                        f"  [!] {result['service']}: {len(result.get('breaches', []))} breaches"
                    )
                elif result.get("status") == "NOT_CONFIGURED":
                    self.print_to_terminal(f"  [!] {result['service']}: NOT CONFIGURED")
                else:
                    self.print_to_terminal(f"  [!] {result['service']}: {result.get('status')}")

            self.print_to_terminal("  [i] Manual email trace links:")
            for dork in generate_dorks(target):
                self.print_to_terminal(f"      [{dork['engine']}] {dork['type']}: {dork['url']}")

            payload = {
                "scan_profile": profile,
                "osint_email": {"target": target, "results": results},
            }
            risk = compute_risk(payload)
            payload["risk"] = risk
            self.print_to_terminal("  Digital Footprint Risk Score")
            self.print_to_terminal(f"    {risk['score']}/100 ({risk['level']})")
            for reason in risk.get("reasons", []):
                sample = ", ".join(str(item) for item in reason.get("evidence", [])[:4])
                if len(reason.get("evidence", [])) > 4:
                    sample += ", ..."
                self.print_to_terminal(
                    f"    [+{reason['points']}] {reason['summary']}: {sample}"
                )
            self.print_to_terminal(f"    {risk['disclaimer']}")

            history = save_and_diff_scan(payload, enabled=bool(self.chk_history.get()))
            self.print_to_terminal("  SCAN DIFF")
            if not history.get("enabled", True):
                self.print_to_terminal("    Local scan history is disabled for this run.")
            elif not history.get("available"):
                self.print_to_terminal(f"    {history.get('message', 'No previous matching scan.')}")
            else:
                previous_risk = history.get("previous", {}).get("risk", {})
                current_risk = history.get("current", {}).get("risk", {})
                previous_profile = history.get("previous", {}).get("profile", "standard")
                current_profile = history.get("current", {}).get("profile", "standard")
                delta = int(history.get("risk_change", {}).get("value", 0))
                if delta > 0:
                    change_label = f"↑ {delta}"
                elif delta < 0:
                    change_label = f"↓ {abs(delta)}"
                else:
                    change_label = "0"
                self.print_to_terminal(
                    f"    Previous Risk: {previous_risk.get('score', 0)} {previous_risk.get('level', 'LOW')}"
                )
                self.print_to_terminal(
                    f"    Current Risk:  {current_risk.get('score', 0)} {current_risk.get('level', 'LOW')}"
                )
                self.print_to_terminal(f"    Previous Profile: {previous_profile}")
                self.print_to_terminal(f"    Current Profile:  {current_profile}")
                self.print_to_terminal(f"    Change: {change_label}")
                self.print_to_terminal(f"    New: {len(history.get('new_findings', []))}")
                self.print_to_terminal(
                    f"    Resolved: {len(history.get('resolved_findings', []))}"
                )
                self.print_to_terminal(
                    f"    Unchanged: {len(history.get('unchanged_findings', []))}"
                )
                if history.get("profile_mismatch"):
                    self.print_to_terminal(f"    {history.get('coverage_warning', '')}")

            correlation = build_identity_correlation(payload)
            self._print_correlation_summary(correlation)
            remediation = build_remediation_report(payload)
            self._print_remediation_actions(remediation)
        finally:
            self.post_ui(self.btn_email.configure, state="normal")

    def start_username_osint(self):
        target = self.osint_entry.get().strip()
        if is_valid_email(target):
            self.print_to_terminal(
                "  [!] That looks like an email address. Use 'Scan Email' for email recon."
            )
            return
        if not is_valid_username_query(target):
            self.print_to_terminal("  [-] ERROR: Username must be 1-100 printable characters.")
            return
        profile = self._selected_profile()
        if not profile_allows_username(profile):
            self.print_to_terminal("  [!] Selected profile does not allow username scans.")
            return
        self.btn_user.configure(state="disabled")
        self.print_to_terminal(
            f"\n[+] OSINT: Initiating username recon for '{target}' using profile '{profile}'"
            f" - {profile_description(profile)}..."
        )
        selected_platforms = select_username_platforms(profile, USERNAME_PLATFORMS)
        self.print_to_terminal(
            f"  -> Username platform pool: {len(selected_platforms)} platforms; "
            f"{len(USERNAME_PLATFORMS) - len(selected_platforms)} excluded."
        )
        self.run_in_thread(self.do_username_osint, target, profile)

    def do_username_osint(self, target: str, profile: str = DEFAULT_SCAN_PROFILE):
        try:
            results = asyncio.run(check_username_async(target, profile=profile))
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

            payload = {
                "scan_profile": profile,
                "osint_username": {"target": target, "results": results},
            }
            risk = compute_risk(payload)
            payload["risk"] = risk
            self.print_to_terminal("  Digital Footprint Risk Score")
            self.print_to_terminal(f"    {risk['score']}/100 ({risk['level']})")
            for reason in risk.get("reasons", []):
                sample = ", ".join(str(item) for item in reason.get("evidence", [])[:4])
                if len(reason.get("evidence", [])) > 4:
                    sample += ", ..."
                self.print_to_terminal(
                    f"    [+{reason['points']}] {reason['summary']}: {sample}"
                )
            self.print_to_terminal(f"    {risk['disclaimer']}")

            history = save_and_diff_scan(payload, enabled=bool(self.chk_history.get()))
            self.print_to_terminal("  SCAN DIFF")
            if not history.get("enabled", True):
                self.print_to_terminal("    Local scan history is disabled for this run.")
            elif not history.get("available"):
                self.print_to_terminal(f"    {history.get('message', 'No previous matching scan.')}")
            else:
                previous_risk = history.get("previous", {}).get("risk", {})
                current_risk = history.get("current", {}).get("risk", {})
                previous_profile = history.get("previous", {}).get("profile", "standard")
                current_profile = history.get("current", {}).get("profile", "standard")
                delta = int(history.get("risk_change", {}).get("value", 0))
                if delta > 0:
                    change_label = f"↑ {delta}"
                elif delta < 0:
                    change_label = f"↓ {abs(delta)}"
                else:
                    change_label = "0"
                self.print_to_terminal(
                    f"    Previous Risk: {previous_risk.get('score', 0)} {previous_risk.get('level', 'LOW')}"
                )
                self.print_to_terminal(
                    f"    Current Risk:  {current_risk.get('score', 0)} {current_risk.get('level', 'LOW')}"
                )
                self.print_to_terminal(f"    Previous Profile: {previous_profile}")
                self.print_to_terminal(f"    Current Profile:  {current_profile}")
                self.print_to_terminal(f"    Change: {change_label}")
                self.print_to_terminal(f"    New: {len(history.get('new_findings', []))}")
                self.print_to_terminal(
                    f"    Resolved: {len(history.get('resolved_findings', []))}"
                )
                self.print_to_terminal(
                    f"    Unchanged: {len(history.get('unchanged_findings', []))}"
                )
                if history.get("profile_mismatch"):
                    self.print_to_terminal(f"    {history.get('coverage_warning', '')}")

            correlation = build_identity_correlation(payload)
            self._print_correlation_summary(correlation)
            remediation = build_remediation_report(payload)
            self._print_remediation_actions(remediation)
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


if __name__ == "__main__":
    app = TrackherApp()
    app.mainloop()
