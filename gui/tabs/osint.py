from __future__ import annotations

import asyncio
from tkinter import messagebox

from gui.widgets.common import ctk, format_result_sample
from osint.checker import check_email
from osint.dorking import generate_dorks
from osint.services import ACCOUNT_PLATFORMS, BREACH_PLATFORMS
from osint.username_checker import USERNAME_PLATFORMS, check_username_async
from utils.correlation import build_identity_correlation
from utils.display import format_username_unknown_breakdown
from utils.history import clear_scan_history, save_and_diff_scan
from utils.helpers import is_valid_email, is_valid_username_query
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
from utils.remediation import build_remediation_report
from utils.risk import compute_risk


class OsintTabMixin:
    """Build and operate the existing OSINT and Platform Health tab."""

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
            self.post_ui(self.lbl_health_summary.configure, text=f"Platform Health: {summary}")
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
            profile, ACCOUNT_PLATFORMS, BREACH_PLATFORMS
        )
        self.print_to_terminal(
            f"  -> Email catalog: {len(account_platforms)} account services; "
            f"{sum(1 for item in account_platforms if item.get('check', 'manual') != 'manual')} "
            f"side-effect-free automatic detectors; {len(breach_platforms)} breach providers; "
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
                if result.get("status") in {"UNKNOWN", "ERROR", "NOT_CONFIGURED"}
            ]
            self.print_to_terminal("  Verified Accounts")
            for result in found:
                detail = f" - {result.get('detail', '')}" if result.get("detail") else ""
                self.print_to_terminal(f"  [+] FOUND: {result['service']}{detail}")
            if not found:
                self.print_to_terminal("    0 verified accounts discovered automatically.")
                self.print_to_terminal("    This does not mean the email has no accounts on other services.")
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
                sample = format_result_sample(unknown, "service")
                self.print_to_terminal(
                    f"  [?] Could not verify {len(unknown)} services"
                    f"{': ' + sample if sample else '.'}"
                )
            self.print_to_terminal("  Manual Investigation")
            if manual:
                self.print_to_terminal(f"    {len(manual)} services require manual review.")
                sample = format_result_sample(manual, "service")
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
            payload = {"scan_profile": profile, "osint_email": {"target": target, "results": results}}
            risk = compute_risk(payload)
            payload["risk"] = risk
            self._print_risk_summary(risk)
            self._print_history_summary(save_and_diff_scan(payload, enabled=bool(self.chk_history.get())))
            self._print_correlation_summary(build_identity_correlation(payload))
            self._print_remediation_actions(build_remediation_report(payload))
        finally:
            self.post_ui(self.btn_email.configure, state="normal")

    def start_username_osint(self):
        target = self.osint_entry.get().strip()
        if is_valid_email(target):
            self.print_to_terminal("  [!] That looks like an email address. Use 'Scan Email' for email recon.")
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
                sample = format_result_sample(unknown, "platform")
                breakdown = format_username_unknown_breakdown(unknown)
                self.print_to_terminal(
                    f"  [?] Could not verify {unknown_count} platforms"
                    f"{' (' + breakdown + ')' if breakdown else ''}"
                    f"{': ' + sample if sample else '.'}"
                )
            self.print_to_terminal(
                f"[!] Total {len(found)} verified matches. "
                f"(Scanned {len(results)}, {unknown_count} could not be verified)"
            )
            payload = {"scan_profile": profile, "osint_username": {"target": target, "results": results}}
            risk = compute_risk(payload)
            payload["risk"] = risk
            self._print_risk_summary(risk)
            self._print_history_summary(save_and_diff_scan(payload, enabled=bool(self.chk_history.get())))
            self._print_correlation_summary(build_identity_correlation(payload))
            self._print_remediation_actions(build_remediation_report(payload))
        finally:
            self.post_ui(self.btn_user.configure, state="normal")

    def do_dork(self):
        target = self.osint_entry.get().strip()
        if not target:
            return
        self.print_to_terminal(f"\n[+] DORK: Generating search links for '{target}'...")
        for dork in generate_dorks(target):
            self.print_to_terminal(f"  [{dork['engine']}] {dork['type']}: {dork['url']}")
