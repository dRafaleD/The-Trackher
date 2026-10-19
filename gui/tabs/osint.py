from __future__ import annotations

import asyncio
from tkinter import messagebox

from gui.widgets.common import ctk, format_result_sample
from osint.checker import check_email
from osint.dorking import generate_dorks
from osint.services import ACCOUNT_PLATFORMS, BREACH_PLATFORMS
from osint.username_checker import (
    USERNAME_PLATFORMS,
    USERNAME_REFERENCE_PLATFORMS,
    check_username_async,
)
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
    profile_request_policy_description,
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
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)
        search = ctk.CTkFrame(tab, fg_color="#152130", corner_radius=12, border_width=1, border_color="#26384b")
        search.grid(row=0, column=0, sticky="ew")
        search.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(search, text="Dijital izlerini keşfet", text_color="#edf4fc", font=ctk.CTkFont(size=21, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(8, 4))
        self.osint_entry = ctk.CTkEntry(search, placeholder_text="Kullanıcı adı, e-posta veya alan adı", height=36, font=self.font_ui, fg_color="#0c1520", border_color="#304459", corner_radius=8)
        self.osint_entry.grid(row=2, column=0, sticky="ew", padx=(20, 10), pady=(0, 8))
        self.btn_user = ctk.CTkButton(search, text="Kullanıcı adı ara", command=self.start_username_osint, height=36, width=150, font=self.font_ui, fg_color="#158ba0", hover_color="#1aa3ba", text_color="#ffffff")
        self.btn_user.grid(row=2, column=1, padx=(0, 10), pady=(0, 8))
        self.btn_email = ctk.CTkButton(search, text="E-posta ara", command=self.start_email_osint, height=36, width=125, font=self.font_ui, fg_color="#233b52", hover_color="#304e6b")
        self.btn_email.grid(row=2, column=2, padx=(0, 10), pady=(0, 8))
        self.btn_dork = ctk.CTkButton(search, text="Arama bağlantıları", command=self.do_dork, height=36, width=140, fg_color="#233b52", hover_color="#304e6b")
        self.btn_dork.grid(row=2, column=3, padx=(0, 20), pady=(0, 8))
        self.btn_domain = ctk.CTkButton(search, text='Alan adı', command=self.start_domain_research, width=100, height=36, fg_color='#233b52', hover_color='#304e6b')
        self.btn_domain.grid(row=2, column=4, padx=(0, 20), pady=(0, 8))
        settings = ctk.CTkFrame(search, fg_color="transparent")
        settings.grid(row=3, column=0, columnspan=5, sticky="ew", padx=20, pady=(0, 8))
        settings.grid_columnconfigure(2, weight=1)
        self.lbl_profile = ctk.CTkLabel(settings, text="Tarama kapsamı", text_color="#91a4ba")
        self.lbl_profile.grid(row=0, column=0, padx=(0, 10))
        self.opt_profile = ctk.CTkOptionMenu(settings, values=list(PROFILE_ORDER), variable=self.profile_var, width=130, fg_color="#23374b", button_color="#304b65", button_hover_color="#40617e")
        self.opt_profile.grid(row=0, column=1)
        self.discover_links_checkbox = ctk.CTkCheckBox(settings, text='Bağlantılardan keşfet', checkbox_width=18, checkbox_height=18, font=ctk.CTkFont(size=12), fg_color='#158ba0')
        self.discover_links_checkbox.grid(row=0, column=2, padx=16, sticky='w')
        self.chk_history = ctk.CTkCheckBox(settings, text="Yerel geçmişe kaydet", font=ctk.CTkFont(size=12), checkbox_width=18, checkbox_height=18, fg_color="#158ba0")
        self.chk_history.grid(row=0, column=3, padx=16)
        self.chk_history.select()
        self.btn_clear_history = ctk.CTkButton(settings, text="Geçmişi temizle", command=self.clear_local_history, width=115, height=28, fg_color="transparent", border_width=1, border_color="#3b4b60", hover_color="#26384b", text_color="#a9bbce")
        self.btn_clear_history.grid(row=0, column=4)
        self.setup_intelligence_controls(search)

        health = ctk.CTkFrame(tab, fg_color="transparent")
        health.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        health.grid_columnconfigure(0, weight=1)
        self.lbl_health_summary = ctk.CTkLabel(health, text="Platform Health: not checked yet", font=ctk.CTkFont(size=11), text_color="#91a4ba", anchor="w", wraplength=620)
        self.lbl_health_summary.grid(row=0, column=0, sticky="w")
        self.chk_health_live = ctk.CTkSwitch(health, text="Canlı kontrol", variable=self.health_live_var, font=ctk.CTkFont(size=12), switch_width=30, switch_height=16, progress_color="#158ba0")
        self.chk_health_live.grid(row=0, column=1, padx=12)
        self.btn_health = ctk.CTkButton(health, text="Platform sağlığı", command=self.start_platform_health_check, width=125, height=28, fg_color="#23374b", hover_color="#304b65")
        self.btn_health.grid(row=0, column=2)
        self.btn_validate = ctk.CTkButton(health, text='Kuralları doğrula', command=self.start_reference_validation, width=125, height=28, fg_color='#23374b', hover_color='#304b65')
        self.btn_validate.grid(row=0, column=3, padx=(8, 0))
        self.setup_scan_results(tab)

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

    def start_reference_validation(self):
        self.btn_validate.configure(state='disabled')
        self.print_to_terminal('  [i] Referans profil ve negatif kontrol çiftleri doğrulanıyor. Son kontroller 24 saat önbellekte tutulur.')
        self.run_in_thread(self.do_platform_health_check, True, True)

    def do_platform_health_check(self, live: bool = False, reference_only: bool = False):
        try:
            result = run_platform_health_check(live=live, **({'reference_only': True} if reference_only else {}))
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
            if self.__dict__.get('results_tree') is not None:
                lines = ['PLATFORM KURALLARININ SAĞLIĞI', '']
                for item in result.get('items', []):
                    lines.append(f"{item.get('platform')} · {item.get('state')}\n  {item.get('detail', '')}\n  Son referans çifti: {item.get('last_reference_success_at') or 'Henüz doğrulanmadı'}")
                self.post_ui(self._show_document, 'Platform sağlığı', '\n'.join(lines))
        finally:
            if self.__dict__.get('btn_validate') is not None:
                self.post_ui(self.btn_validate.configure, state='normal')
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
        self.print_to_terminal(f"  -> Network policy: {profile_request_policy_description(profile)}")
        account_platforms, breach_platforms = select_email_platforms(
            profile, ACCOUNT_PLATFORMS, BREACH_PLATFORMS
        )
        self.print_to_terminal(
            f"  -> Email catalog: {len(account_platforms)} account services; "
            f"{sum(1 for item in account_platforms if item.get('check', 'manual') != 'manual')} "
            f"side-effect-free automatic detectors; {len(breach_platforms)} breach providers; "
            f"{len(ACCOUNT_PLATFORMS) - len(account_platforms)} account services excluded."
        )
        self._prepare_scan_context('email', target, profile)
        self._begin_scan_results(len(account_platforms) + len(breach_platforms) + 1, 'E-posta')
        self.run_in_thread(self.do_email_osint, target, profile)

    def do_email_osint(self, target: str, profile: str = DEFAULT_SCAN_PROFILE):
        try:
            kwargs = self._scan_kwargs()
            if self.__dict__.get('_scan_control') is not None:
                def stream_email(result):
                    if result.get('section') == 'domain':
                        result['service'] = 'Email domain'
                    self.post_ui(self._receive_scan_result, result)
                kwargs['on_result'] = stream_email
            results = asyncio.run(check_email(target, profile=profile, **kwargs))
            if not results:
                self.print_to_terminal("  [!] WARNING: Email scan returned no service results.")
                return
            accounts = results.get("accounts", []) if isinstance(results, dict) else results
            breaches = results.get("breaches", []) if isinstance(results, dict) else []
            if self.__dict__.get('results_tree') is not None:
                rows = list(accounts) + list(breaches)
                if isinstance(results, dict) and results.get('domain'):
                    domain = results['domain']
                    rows.append(dict(domain, service='Email domain' if self.__dict__.get('_scan_control') is not None else f"Alan adı · {domain.get('domain', '')}"))
                self.post_ui(self._complete_scan_results, self._merge_results(rows))
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
                for result in unknown:
                    if result.get("unknown_cause") == "rate_limited":
                        self.print_to_terminal(
                            f"  [PAUSED] {result['service']}: "
                            "site paused; skipped because of rate limiting."
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
            self._print_history_summary(save_and_diff_scan(payload, enabled=self._saved_history_choice()))
            self._print_correlation_summary(build_identity_correlation(payload))
            self._print_remediation_actions(build_remediation_report(payload))
        finally:
            if self.__dict__.get('results_tree') is not None:
                self.post_ui(self._release_scan_results)
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
        self.print_to_terminal(f"  -> Network policy: {profile_request_policy_description(profile)}")
        selected_platforms = select_username_platforms(profile, USERNAME_PLATFORMS)
        self.print_to_terminal(
            f"  -> Username platform pool: {len(selected_platforms)} platforms; "
            f"{len(USERNAME_PLATFORMS) - len(selected_platforms)} excluded."
        )
        reference_count = sum(
            1 for item in selected_platforms if item.get("reference_username")
        )
        self.print_to_terminal(
            f"  -> Reliable reference core: {reference_count}/{len(USERNAME_REFERENCE_PLATFORMS)} "
            "platforms run first; matches are shown immediately."
        )
        self._prepare_scan_context('username', target, profile)
        self._begin_scan_results(len(selected_platforms), 'Kullanıcı adı')
        self.run_in_thread(self.do_username_osint, target, profile)

    def do_username_osint(self, target: str, profile: str = DEFAULT_SCAN_PROFILE):
        try:
            streamed_found: set[tuple[str, str]] = set()

            def stream_result(result: dict) -> None:
                if self.__dict__.get('results_tree') is not None:
                    self.post_ui(self._receive_scan_result, dict(result))
                if result.get("unknown_cause") == "rate_limited":
                    self.print_to_terminal(
                        f"  [PAUSED] {result.get('platform', 'Site')}: "
                        "site paused; skipped because of rate limiting."
                    )
                    return
                if not result.get("found"):
                    return
                key = (str(result.get("platform", "")), str(result.get("url", "")))
                if key in streamed_found:
                    return
                streamed_found.add(key)
                self.print_to_terminal(f"  [+] FOUND: {key[0]} -> {key[1]}")

            results = asyncio.run(
                check_username_async(target, profile=profile, on_result=stream_result,
                    **({'discover_links': True} if self.__dict__.get('_discover_links_enabled') else {}), **self._scan_kwargs())
            )
            results = self._merge_results(results)
            if self.__dict__.get('results_tree') is not None:
                self.post_ui(self._complete_scan_results, results)
            if not results:
                self.print_to_terminal("  [!] WARNING: Username scan returned no platform results.")
                return
            found = [result for result in results if result["found"]]
            unknown = [result for result in results if result.get("status") == "unknown"]
            unknown_count = len(unknown)
            for result in found:
                key = (str(result.get("platform", "")), str(result.get("url", "")))
                if key not in streamed_found:
                    self.print_to_terminal(f"  [+] FOUND: {key[0]} -> {key[1]}")
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
            self._print_history_summary(save_and_diff_scan(payload, enabled=self._saved_history_choice()))
            self._print_correlation_summary(build_identity_correlation(payload))
            self._print_remediation_actions(build_remediation_report(payload))
        finally:
            if self.__dict__.get('results_tree') is not None:
                self.post_ui(self._release_scan_results)
            self.post_ui(self.btn_user.configure, state="normal")

    def start_domain_research(self):
        from osint.domain_research import normalize_domain
        target = self.osint_entry.get().strip()
        if is_valid_email(target):
            target = target.rsplit('@', 1)[-1]
        try:
            target = normalize_domain(target)
        except ValueError:
            self.print_to_terminal('  [-] ERROR: example.com biçiminde bir alan adı girin.')
            return
        self._prepare_scan_context('domain', target)
        self._begin_scan_results(9, 'Alan adı')
        self.run_in_thread(self.do_domain_research, target)

    def do_domain_research(self, target):
        from osint.domain_research import research_domain
        from osint.evidence import evidence_card
        try:
            async def controlled_domain():
                from osint.scan_control import ScanStopped
                control = self.__dict__.get('_scan_control')
                try:
                    if control is not None:
                        return await control.run('DNS / RDAP / SPF / DMARC / DNSSEC / CT', lambda: research_domain(target, enhanced=True, certificates=True))
                    return await research_domain(target, enhanced=True, certificates=True)
                except ScanStopped:
                    return None
            report = asyncio.run(controlled_domain())
            if report is None:
                self.post_ui(self._complete_scan_results, [{'service': target, 'status': 'UNKNOWN', 'detail': 'Tarama durduruldu', 'unknown_cause': 'cancelled'}])
                return
            rows = []
            for name, record in list(report['dns'].items()) + [('RDAP', report['rdap'])] + list(report.get('security', {}).items()):
                descriptions = {'missing': 'Kayıt bulunamadı', 'multiple_records': 'Birden fazla politika kaydı var; yapılandırmayı inceleyin',
                                'permits_all': 'SPF tüm göndericilere izin veriyor', 'policy_present': 'SPF kaydı var; tam politika değerlendirmesi yapılmadı',
                                'monitoring_only': 'DMARC p=none: yalnızca izleme', 'enforcement_policy': f'DMARC politikası: {record.get("policy", "")}',
                                'invalid_policy': 'DMARC politikası eksik veya geçersiz', 'validated_by_resolver': 'DNSSEC yanıtı çözücü tarafından doğrulandı',
                                'not_authenticated': 'DNSSEC yanıtı doğrulanmış olarak işaretlenmedi', 'unknown': 'Doğrulanamadı'}
                detail = descriptions.get(record.get('assessment')) or record.get('reason') or record['status']
                if name == 'Certificate transparency' and record['status'] == 'FOUND':
                    detail = f'{len(record.get("names", []))} sertifika adayı; çalışan hizmet kanıtı değildir'
                row = {'service': f'{target} · {name}', 'status': record['status'],
                       'url': record.get('source_url', ''), 'detail': detail,
                       'public_metadata': {key: value for key, value in record.items() if key in ('records', 'events', 'nameservers', 'handle', 'registrar_handles', 'assessment', 'policy', 'dnssec_authenticated', 'names', 'limitations')}}
                row['evidence_card'] = evidence_card(row, detector=name)
                rows.append(row)
            self.post_ui(self._complete_scan_results, rows)
            self.print_to_terminal(f'  [i] Alan adı araştırması tamamlandı: {target} · {report["status"]}')
        finally:
            self.post_ui(self._release_scan_results)

    def do_dork(self):
        target = self.osint_entry.get().strip()
        if not target:
            return
        self.print_to_terminal(f"\n[+] DORK: Generating search links for '{target}'...")
        for dork in generate_dorks(target):
            self.print_to_terminal(f"  [{dork['engine']}] {dork['type']}: {dork['url']}")
