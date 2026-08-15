from __future__ import annotations

import json
from datetime import datetime
from html import escape
from urllib.parse import urlparse

from utils.display import print_error, print_success


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


def export_to_json(data: dict, filepath: str) -> None:
    """Save results as a JSON report."""
    try:
        with open(filepath, "w", encoding="utf-8") as file_obj:
            json.dump(data, file_obj, ensure_ascii=False, indent=4)
        print_success(f"JSON raporu kaydedildi: {filepath}")
    except OSError as exc:
        print_error(f"JSON raporu kaydedilemedi: {exc}")


def export_to_html(data: dict, filepath: str) -> None:
    """Save results as an HTML report."""
    try:
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
        """

        if "osint_email" in data:
            email = _html(data["osint_email"]["target"])
            results = data["osint_email"]["results"]
            found_count = sum(1 for result in results if result["found"])
            unknown_count = sum(1 for result in results if result.get("status") == "unknown")
            skipped_count = sum(1 for result in results if result.get("status") == "skipped")

            html_content += f"""
                <section class="section">
                    <h2>E-posta OSINT</h2>
                    <p><strong>Hedef:</strong> <code>{email}</code></p>
                    <p>
                        <strong>{found_count}</strong> doğrulanmış kayıt bulundu.
                        <strong>{unknown_count}</strong> sonuç doğrulanamadı.
                        <strong>{skipped_count}</strong> riskli sorgu güvenlik nedeniyle atlandı.
                    </p>
                    <table>
                        <tr><th>Servis</th><th>Durum</th><th>Detay</th></tr>
            """
            for result in results:
                detail_value = result.get("detail", "")
                result_status = result.get(
                    "status", "found" if result.get("found") else "not_found"
                )
                status_class = {
                    "found": "found",
                    "unknown": "unknown",
                    "skipped": "skipped",
                    "not_found": "not-found",
                }.get(result_status, "unknown")
                status_text = {
                    "found": "Bulundu",
                    "unknown": "Doğrulanamadı",
                    "skipped": "Atlandı",
                    "not_found": "Bulunamadı",
                }.get(result_status, "Doğrulanamadı")
                service = _html(result.get("service", "Bilinmiyor"))
                detail = _html(detail_value)
                html_content += f"""
                    <tr>
                        <td>{service}</td>
                        <td class="{status_class}">{status_text}</td>
                        <td>{detail}</td>
                    </tr>
                """
            html_content += """
                    </table>
                </section>
            """

        if "osint_username" in data:
            username = _html(data["osint_username"]["target"])
            results = data["osint_username"]["results"]
            found_count = sum(1 for result in results if result["found"])
            unknown_count = sum(1 for result in results if result.get("status") == "unknown")

            html_content += f"""
                <section class="section">
                    <h2>Kullanici Adi OSINT</h2>
                    <p><strong>Hedef:</strong> <code>{username}</code></p>
                    <p>
                        <strong>{found_count}</strong> platformda kayıt bulundu.
                        <strong>{unknown_count}</strong> sonuç doğrulanamadı.
                    </p>
                    <table>
                        <tr><th>Platform</th><th>URL</th><th>Durum</th></tr>
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
                html_content += f"""
                    <tr>
                        <td>{platform_name}</td>
                        <td>{_link_cell(url)}</td>
                        <td class="{status_class}">{status_text}</td>
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
                    <h2>Arama Motoru Dork Sonuclari</h2>
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
                    <h2>Sistem Temizligi</h2>
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
                    Üreten: Trackher - açık kaynak dijital ayak izi temizleme ve OSINT aracı
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
