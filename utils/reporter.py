from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from html import escape
from urllib.parse import urlparse

from utils.display import (
    format_username_unknown_breakdown,
    print_error,
    print_success,
    username_unknown_cause_label,
)
from utils.correlation import build_identity_correlation
from utils.risk import compute_risk
from utils.remediation import build_remediation_report


def _html(value: object) -> str:
    return escape(str(value), quote=True)


def _safe_url(value: object) -> str:
    text = str(value)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return _html(text)


def _link_cell(url: str, label: str | None = None) -> str:
    if not url:
        return '<span style="color: #888;">Geçersiz veya kullanılamayan bağlantı</span>'
    visible_label = _html(label) if label else url
    return (
        f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
        f'style="color: #4da6ff;">{visible_label}</a>'
    )


UNRELIABLE_WARNING = "Bu platform heuristik olarak taranir; sonucu manuel dogrulayin."


def _prepare_report_data(data: dict) -> dict:
    prepared = deepcopy(data)

    username_section = prepared.get("osint_username")
    if isinstance(username_section, dict):
        results = username_section.get("results")
        if isinstance(results, list):
            for result in results:
                if (
                    isinstance(result, dict)
                    and result.get("reliability") == "unreliable"
                ):
                    result["warning"] = UNRELIABLE_WARNING

    if any(key in prepared for key in ("osint_email", "osint_username")):
        prepared.setdefault("scan_profile", "standard")

    if "risk" not in prepared and any(
        key in prepared for key in ("osint_email", "osint_username")
    ):
        prepared["risk"] = compute_risk(prepared)

    if "remediation" not in prepared and any(
        key in prepared for key in ("osint_email", "osint_username")
    ):
        prepared["remediation"] = build_remediation_report(prepared)

    if "correlation" not in prepared and any(
        key in prepared for key in ("osint_email", "osint_username")
    ):
        prepared["correlation"] = build_identity_correlation(prepared)

    return prepared


def _render_risk_section(risk: dict) -> str:
    score = int(risk.get("score", 0))
    level = _html(risk.get("level", "LOW"))
    disclaimer = _html(risk.get("disclaimer", ""))
    reasons = risk.get("reasons", [])

    level_class = {
        "LOW": "found",
        "MEDIUM": "unknown",
        "HIGH": "not-found",
        "CRITICAL": "not-found",
    }.get(level, "unknown")

    if reasons:
        rows = []
        for reason in reasons:
            summary = _html(reason.get("summary", "Evidence"))
            points = _html(reason.get("points", 0))
            evidence = ", ".join(_html(item) for item in reason.get("evidence", []))
            detail = _html(reason.get("detail", ""))
            rows.append(
                f"<tr><td>{summary}</td><td>+{points}</td><td>{evidence}</td><td>{detail}</td></tr>"
            )
        reasons_html = "".join(rows)
    else:
        reasons_html = (
            '<tr><td colspan="4" style="color: var(--muted);">'
            "No verified or heuristic exposure evidence increased the score."
            "</td></tr>"
        )

    return f"""
        <section class="section">
            <h2>Digital Footprint Risk Score</h2>
            <p><strong class="{level_class}">{score}/100 ({level})</strong></p>
            <p>{disclaimer}</p>
            <table>
                <tr><th>Reason</th><th>Points</th><th>Evidence</th><th>Why it matters</th></tr>
                {reasons_html}
            </table>
        </section>
    """


def _render_scan_diff_section(diff: dict) -> str:
    if not diff.get("enabled", True):
        return """
        <section class="section">
            <h2>Scan Diff</h2>
            <p>Local scan history was disabled for this run.</p>
        </section>
        """

    if not diff.get("available"):
        message = _html(diff.get("message", "No previous matching scan in local history."))
        return f"""
        <section class="section">
            <h2>Scan Diff</h2>
            <p>{message}</p>
        </section>
        """

    previous_risk = diff.get("previous", {}).get("risk", {})
    current_risk = diff.get("current", {}).get("risk", {})
    previous_profile = _html(diff.get("previous", {}).get("profile", "standard"))
    current_profile = _html(diff.get("current", {}).get("profile", "standard"))
    coverage_warning = ""
    if diff.get("profile_mismatch"):
        coverage_warning = f"<p><strong>Coverage Warning:</strong> {_html(diff.get('coverage_warning', ''))}</p>"
    risk_change = int(diff.get("risk_change", {}).get("value", 0))
    if risk_change > 0:
        change_label = f"↑ {risk_change}"
    elif risk_change < 0:
        change_label = f"↓ {abs(risk_change)}"
    else:
        change_label = "0"

    def labels(items: list[dict], empty: str) -> str:
        if not items:
            return f'<tr><td colspan="2" style="color: var(--muted);">{empty}</td></tr>'
        return "".join(
            f"<tr><td>{_html(item.get('label', 'Unknown'))}</td><td>{_html(item.get('status', 'FOUND'))}</td></tr>"
            for item in items
        )

    return f"""
        <section class="section">
            <h2>Scan Diff</h2>
            <p><strong>Previous Risk:</strong> {previous_risk.get('score', 0)} {_html(previous_risk.get('level', 'LOW'))}</p>
            <p><strong>Current Risk:</strong> {current_risk.get('score', 0)} {_html(current_risk.get('level', 'LOW'))}</p>
            <p><strong>Previous Profile:</strong> {previous_profile}</p>
            <p><strong>Current Profile:</strong> {current_profile}</p>
            <p><strong>Change:</strong> {change_label}</p>
            <p><strong>New:</strong> {len(diff.get('new_findings', []))}</p>
            <p><strong>Resolved:</strong> {len(diff.get('resolved_findings', []))}</p>
            <p><strong>Unchanged:</strong> {len(diff.get('unchanged_findings', []))}</p>
            <p><strong>New Breaches:</strong> {len(diff.get('new_breaches', []))}</p>
            <p><strong>Removed Breaches:</strong> {len(diff.get('removed_breaches', []))}</p>
            {coverage_warning}
            <h3>New Findings</h3>
            <table><tr><th>Label</th><th>Status</th></tr>{labels(diff.get('new_findings', []), "No new findings.")}</table>
            <h3>Resolved Findings</h3>
            <table><tr><th>Label</th><th>Status</th></tr>{labels(diff.get('resolved_findings', []), "No resolved findings.")}</table>
            <h3>New Breaches</h3>
            <table><tr><th>Label</th><th>Status</th></tr>{labels(diff.get('new_breaches', []), "No new breaches.")}</table>
            <h3>Removed Breaches</h3>
            <table><tr><th>Label</th><th>Status</th></tr>{labels(diff.get('removed_breaches', []), "No removed breaches.")}</table>
        </section>
    """


def _render_remediation_section(remediation: dict) -> str:
    if not remediation.get("available"):
        return """
        <section class="section">
            <h2>Remediation / Privacy Actions</h2>
            <p>No official remediation links were matched for the current scan.</p>
        </section>
        """

    rows = []
    for item in remediation.get("items", []):
        platform = _html(item.get("platform", "Unknown"))
        status = _html(item.get("status", "FOUND"))
        action_cells = []
        for action in item.get("actions", []):
            label = str(action.get("label", "Action"))
            url = _safe_url(action.get("url", ""))
            action_cells.append(_link_cell(url, label))
        actions_html = "<br>".join(action_cells) if action_cells else '<span style="color: var(--muted);">No official links.</span>'
        rows.append(f"<tr><td>{platform}</td><td>{status}</td><td>{actions_html}</td></tr>")

    return f"""
        <section class="section">
            <h2>Remediation / Privacy Actions</h2>
            <p>{_html(remediation.get("item_count", 0))} findings include {_html(remediation.get("action_count", 0))} official links.</p>
            <table>
                <tr><th>Platform</th><th>Status</th><th>Actions</th></tr>
                {''.join(rows)}
            </table>
        </section>
    """


def _render_correlation_section(correlation: dict) -> str:
    if not correlation.get("available"):
        return """
        <section class="section">
            <h2>Identity Correlation</h2>
            <p>No conservative multi-signal identity correlations were established from the current scan.</p>
        </section>
        """

    rows = []
    for item in correlation.get("items", []):
        summary = _html(item.get("summary", "Unknown pair"))
        confidence = _html(item.get("confidence", "LOW"))
        score = _html(item.get("confidence_score", 0))
        evidence = []
        for entry in item.get("evidence", []):
            prefix = "✓" if entry.get("strength") in {"strong", "medium"} else "~"
            label = _html(entry.get("label", "signal"))
            value = _html(entry.get("value", ""))
            evidence.append(f"{prefix} {label}{': ' + value if value else ''}")
        penalties = []
        for entry in item.get("penalties", []):
            penalties.append(f"! {_html(entry.get('label', 'penalty'))}")
        detail = "<br>".join(evidence + penalties) if (evidence or penalties) else '<span style="color: var(--muted);">No evidence.</span>'
        rows.append(f"<tr><td>{summary}</td><td>{confidence} ({score}/100)</td><td>{detail}</td></tr>")

    return f"""
        <section class="section">
            <h2>Identity Correlation</h2>
            <p>{_html(correlation.get("disclaimer", ""))}</p>
            <table>
                <tr><th>Pair</th><th>Confidence</th><th>Evidence</th></tr>
                {''.join(rows)}
            </table>
        </section>
    """


def _render_platform_health_section(health: dict) -> str:
    if not health.get("available"):
        return ""

    counts = dict(health.get("counts", {}))
    rows = []
    for item in health.get("items", [])[:40]:
        rows.append(
            "<tr>"
            f"<td>{_html(item.get('scope', 'platform'))}</td>"
            f"<td>{_html(item.get('platform', 'Unknown'))}</td>"
            f"<td>{_html(item.get('detector', 'unknown'))}</td>"
            f"<td>{_html(item.get('state', 'UNKNOWN'))}</td>"
            f"<td>{_html(item.get('detail', ''))}</td>"
            "</tr>"
        )

    mode_text = "Offline schema + safe live probes" if health.get("live_enabled") else "Offline schema only"
    return f"""
        <section class="section">
            <h2>Platform / Detector Health</h2>
            <p><strong>Mode:</strong> {mode_text}</p>
            <p><strong>Summary:</strong> Healthy: {counts.get('HEALTHY', 0)} | Degraded: {counts.get('DEGRADED', 0)} | Broken: {counts.get('BROKEN', 0)} | Unknown: {counts.get('UNKNOWN', 0)}</p>
            <p><strong>Cache Hits:</strong> {_html(health.get('cache_hits', 0))}</p>
            <table>
                <tr><th>Scope</th><th>Platform</th><th>Detector</th><th>State</th><th>Detail</th></tr>
                {''.join(rows)}
            </table>
        </section>
    """


def _render_email_section(email_data: dict) -> str:
    email = _html(email_data["target"])
    results = email_data["results"]
    accounts = results.get("accounts", []) if isinstance(results, dict) else results
    breaches = results.get("breaches", []) if isinstance(results, dict) else []
    verified = [item for item in accounts if item.get("status") == "FOUND"]
    possible = [item for item in accounts if item.get("status") == "POSSIBLE"]
    not_found = [item for item in accounts if item.get("status") == "NOT_FOUND"]
    manual = [item for item in accounts if item.get("status") == "MANUAL"]
    unknown = [item for item in accounts if item.get("status") in {"UNKNOWN", "ERROR", "NOT_CONFIGURED"}]

    def rows(items: list[dict], empty: str) -> str:
        if not items:
            return f'<tr><td colspan="3" style="color: var(--muted);">{empty}</td></tr>'
        html_rows = []
        for item in items:
            service = _html(item.get("service", "Bilinmiyor"))
            status = _html(item.get("status", "UNKNOWN"))
            detail = _html(item.get("detail", ""))
            html_rows.append(f"<tr><td>{service}</td><td>{status}</td><td>{detail}</td></tr>")
        return "\n".join(html_rows)

    breach_rows = []
    for item in breaches:
        service = _html(item.get("service", "Bilinmiyor"))
        status = _html(item.get("status", "UNKNOWN"))
        detail = _html(item.get("detail", ""))
        if item.get("status") == "FOUND":
            detail = _html(f"{len(item.get('breaches', []))} breaches")
        elif item.get("status") == "NOT_CONFIGURED":
            detail = "NOT CONFIGURED"
        breach_rows.append(f"<tr><td>{service}</td><td>{status}</td><td>{detail}</td></tr>")
    if not breach_rows:
        breach_rows.append('<tr><td colspan="3" style="color: var(--muted);">No breach providers.</td></tr>')

    zero_message = ""
    if not verified:
        zero_message = """
            <p>
                <strong>0 verified accounts discovered automatically.</strong>
                This does not mean the email has no accounts on other services.
            </p>
        """

    return f"""
        <section class="section">
            <h2>E-posta OSINT</h2>
            <p><strong>Hedef:</strong> <code>{email}</code></p>
            {zero_message}
            <h3>Verified Accounts</h3>
            <table><tr><th>Service</th><th>Status</th><th>Detail</th></tr>{rows(verified, "No verified accounts.")}</table>
            <h3>Possible Accounts</h3>
            <table><tr><th>Service</th><th>Status</th><th>Detail</th></tr>{rows(possible, "No possible heuristic matches.")}</table>
            <h3>Checked and Not Found</h3>
            <table><tr><th>Service</th><th>Status</th><th>Detail</th></tr>{rows(not_found, "No reliably absent services.")}</table>
            <h3>Unknown / Errors</h3>
            <table><tr><th>Service</th><th>Status</th><th>Detail</th></tr>{rows(unknown, "No unknown account checks.")}</table>
            <h3>Manual Investigation</h3>
            <p>Manual entries are investigation leads, not failed checks.</p>
            <table><tr><th>Service</th><th>Status</th><th>Detail</th></tr>{rows(manual, "No manual services.")}</table>
            <h3>Breaches</h3>
            <table><tr><th>Provider</th><th>Status</th><th>Detail</th></tr>{''.join(breach_rows)}</table>
        </section>
    """


def export_to_json(data: dict, filepath: str) -> None:
    """Save results as a JSON report."""
    try:
        payload = _prepare_report_data(data)
        with open(filepath, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=4)
        print_success(f"JSON raporu kaydedildi: {filepath}")
    except OSError as exc:
        print_error(f"JSON raporu kaydedilemedi: {exc}")


def export_to_html(data: dict, filepath: str) -> None:
    """Save results as an HTML report."""
    try:
        prepared = _prepare_report_data(data)
        html_content = f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Trackher Raporu</title>
            <style>
                :root {{
                    color-scheme: dark;
                    --bg: #0f141b;
                    --panel: #18202a;
                    --panel-strong: #202a36;
                    --text: #edf2f7;
                    --muted: #98a4b3;
                    --accent: #3dc2ff;
                    --success: #4ade80;
                    --warn: #fbbf24;
                    --skip: #67e8f9;
                    --danger: #f87171;
                    --border: #2c3a4a;
                }}
                * {{ box-sizing: border-box; }}
                body {{
                    margin: 0;
                    padding: 32px 20px;
                    font-family: "Segoe UI", "Inter", sans-serif;
                    background:
                        radial-gradient(circle at top, rgba(61, 194, 255, 0.10), transparent 32%),
                        linear-gradient(180deg, #0b1016 0%, var(--bg) 100%);
                    color: var(--text);
                }}
                .container {{
                    max-width: 1040px;
                    margin: 0 auto;
                    background: rgba(24, 32, 42, 0.92);
                    border: 1px solid var(--border);
                    border-radius: 20px;
                    padding: 28px;
                    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.32);
                }}
                h1, h2 {{
                    margin: 0 0 12px;
                    color: var(--accent);
                }}
                p {{
                    color: var(--text);
                    line-height: 1.6;
                }}
                .meta {{
                    margin-bottom: 28px;
                    color: var(--muted);
                }}
                .section {{
                    margin-top: 28px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 14px;
                    overflow: hidden;
                    border-radius: 14px;
                    background: rgba(15, 20, 27, 0.45);
                }}
                th, td {{
                    padding: 12px 14px;
                    text-align: left;
                    border-bottom: 1px solid var(--border);
                    vertical-align: top;
                }}
                th {{
                    background: var(--panel-strong);
                    color: var(--accent);
                }}
                .found {{ color: var(--success); font-weight: 700; }}
                .not-found {{ color: var(--danger); }}
                .unknown {{ color: var(--warn); }}
                .skipped {{ color: var(--skip); }}
                .footer {{
                    margin-top: 28px;
                    color: var(--muted);
                    font-size: 0.95rem;
                }}
                code {{
                    font-family: "Cascadia Code", "Consolas", monospace;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Trackher Raporu</h1>
                <p class="meta"><strong>Oluşturulma:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                <p class="meta"><strong>Scan Profile:</strong> {_html(prepared.get('scan_profile', 'standard'))}</p>
        """

        if "risk" in prepared:
            html_content += _render_risk_section(prepared["risk"])

        if "scan_history" in prepared:
            html_content += _render_scan_diff_section(prepared["scan_history"])

        if "platform_health" in prepared:
            html_content += _render_platform_health_section(prepared["platform_health"])

        if "correlation" in prepared:
            html_content += _render_correlation_section(prepared["correlation"])

        if "remediation" in prepared:
            html_content += _render_remediation_section(prepared["remediation"])

        if "osint_email" in prepared:
            html_content += _render_email_section(prepared["osint_email"])

        if "osint_username" in prepared:
            username = _html(prepared["osint_username"]["target"])
            results = prepared["osint_username"]["results"]
            found_count = sum(1 for result in results if result["found"])
            unknown_count = sum(1 for result in results if result.get("status") == "unknown")
            unknown_breakdown = _html(format_username_unknown_breakdown(results))

            html_content += f"""
                <section class="section">
                    <h2>Kullanıcı Adı OSINT</h2>
                    <p><strong>Hedef:</strong> <code>{username}</code></p>
                    <p>
                        <strong>{found_count}</strong> platformda kayıt bulundu.
                        <strong>{unknown_count}</strong> sonuç doğrulanamadı.
                    </p>
                    <p><strong>Doğrulanamayan nedenler:</strong> {unknown_breakdown or 'Yok'}</p>
                    <table>
                        <tr><th>Platform</th><th>URL</th><th>Durum</th><th>Neden</th></tr>
            """
            for result in results:
                result_status = result.get(
                    "status", "found" if result.get("found") else "not_found"
                )
                status_class = {
                    "found": "found",
                    "unknown": "unknown",
                    "not_found": "not-found",
                }.get(result_status, "unknown")
                status_text = {
                    "found": "Bulundu",
                    "unknown": "Doğrulanamadı",
                    "not_found": "Bulunamadı",
                }.get(result_status, "Doğrulanamadı")
                platform_name = _html(result.get("platform", "Bilinmiyor"))
                url = _safe_url(result.get("url", ""))
                warning = result.get("warning", "")
                cause = ""
                if result_status == "unknown":
                    cause = _html(username_unknown_cause_label(result.get("unknown_cause")))
                warning_html = (
                    f'<br><span class="unknown">{_html(warning)}</span>'
                    if warning
                    else ""
                )
                html_content += f"""
                    <tr>
                        <td>{platform_name}</td>
                        <td>{_link_cell(url)}</td>
                        <td class="{status_class}">{status_text}{warning_html}</td>
                        <td>{cause}</td>
                    </tr>
                """
            html_content += """
                    </table>
                </section>
            """

        if "osint_dork" in data:
            target = _html(data["osint_dork"]["target"])
            dorks = data["osint_dork"]["dorks"]

            html_content += f"""
                <section class="section">
                    <h2>Arama Motoru Dork Sonuçları</h2>
                    <p><strong>Hedef:</strong> <code>{target}</code></p>
                    <p>Bağlantılar, tarayıcıda manuel inceleme yapabilmeniz için üretilir.</p>
                    <table>
                        <tr><th>Arama Motoru</th><th>Tur</th><th>Baglanti</th></tr>
            """
            for dork in dorks:
                engine = _html(dork.get("engine", "Bilinmiyor"))
                dork_type = _html(dork.get("type", "Bilinmiyor"))
                url = _safe_url(dork.get("url", ""))
                html_content += f"""
                    <tr>
                        <td>{engine}</td>
                        <td>{dork_type}</td>
                        <td>{_link_cell(url, "Aç ve incele")}</td>
                    </tr>
                """
            html_content += """
                    </table>
                </section>
            """

        if "cleaning" in data:
            items = data["cleaning"]["items"]
            total_size = data["cleaning"]["total_size_bytes"]
            is_dry_run = data["cleaning"].get("is_dry_run", False)

            mode_text = "Simulasyon" if is_dry_run else "Uygulandi"
            html_content += f"""
                <section class="section">
                    <h2>Sistem Temizliği</h2>
                    <p><strong>Mod:</strong> {mode_text}</p>
                    <p>Toplam <strong>{len(items)}</strong> öğe, <strong>{total_size / (1024 * 1024):.2f} MB</strong> alan.</p>
                    <table>
                        <tr><th>Tur</th><th>Yol</th><th>Boyut (Bayt)</th></tr>
            """
            for item in items:
                item_type = _html(item.get("type", "Bilinmiyor"))
                item_path = _html(item.get("path", ""))
                item_size = _html(item.get("size", 0))
                html_content += f"""
                    <tr>
                        <td>{item_type}</td>
                        <td>{item_path}</td>
                        <td>{item_size}</td>
                    </tr>
                """
            html_content += """
                    </table>
                </section>
            """

        html_content += """
                <div class="footer">
                    Üreten: Trackher - açık kaynak dijital ayak izi temizleme ve username OSINT aracı
                </div>
            </div>
        </body>
        </html>
        """

        with open(filepath, "w", encoding="utf-8") as file_obj:
            file_obj.write(html_content)
        print_success(f"HTML raporu kaydedildi: {filepath}")
    except OSError as exc:
        print_error(f"HTML raporu kaydedilemedi: {exc}")


def generate_report(data: dict, output_path: str, format_type: str = "html") -> None:
    """Generate a report in the selected format."""
    if format_type.lower() == "json":
        if not output_path.endswith(".json"):
            output_path += ".json"
        export_to_json(data, output_path)
    else:
        if not output_path.endswith(".html"):
            output_path += ".html"
        export_to_html(data, output_path)
