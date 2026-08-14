import json
from datetime import datetime
from html import escape
from utils.display import print_success, print_error


def _html(value: object) -> str:
    return escape(str(value), quote=True)

def export_to_json(data: dict, filepath: str) -> None:
    """Sonuçları JSON dosyası olarak kaydeder."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print_success(f"JSON Raporu kaydedildi: {filepath}")
    except Exception as e:
        print_error(f"JSON raporu kaydedilemedi: {e}")

def export_to_html(data: dict, filepath: str) -> None:
    """Sonuçları HTML dosyası olarak kaydeder."""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Dijital Ayak İzi Raporu</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 20px; }}
                h1, h2 {{ color: #00d2ff; }}
                .container {{ max-width: 900px; margin: auto; background: #1e1e1e; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #333; }}
                th {{ background-color: #2a2a2a; color: #00d2ff; }}
                .found {{ color: #00ff88; font-weight: bold; }}
                .not-found {{ color: #ff4d4d; }}
                .unknown {{ color: #ffc857; }}
                .error {{ color: #ffa500; }}
                .footer {{ margin-top: 30px; text-align: center; font-size: 0.9em; color: #888; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🛡️ Dijital Ayak İzi Raporu</h1>
                <p><strong>Tarih:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        """

        if "osint_email" in data:
            email = _html(data["osint_email"]["target"])
            results = data["osint_email"]["results"]
            found_count = sum(1 for r in results if r["found"])
            
            html_content += f"""
                <h2>E-posta OSINT ({email})</h2>
                <p>Toplam <strong>{found_count}</strong> platformda kayıt bulundu.</p>
                <table>
                    <tr><th>Platform</th><th>Durum</th><th>Detay</th></tr>
            """
            for res in results:
                detail_value = res.get("detail", "")
                status_class = "found" if res["found"] else ("not-found" if detail_value == "" else "error")
                status_text = "Bulundu" if res["found"] else ("Bulunamadı" if detail_value == "" else "Hata")
                service = _html(res.get("service", "Bilinmiyor"))
                detail = _html(detail_value)
                html_content += f"""
                    <tr>
                        <td>{service}</td>
                        <td class="{status_class}">{status_text}</td>
                        <td>{detail}</td>
                    </tr>
                """
            html_content += "</table>"
            
        if "osint_username" in data:
            username = _html(data["osint_username"]["target"])
            results = data["osint_username"]["results"]
            found_count = sum(1 for r in results if r["found"])
            
            html_content += f"""
                <h2>Kullanıcı Adı OSINT ({username})</h2>
                <p>Toplam <strong>{found_count}</strong> platformda kayıt bulundu.</p>
                <table>
                    <tr><th>Platform</th><th>URL</th><th>Durum</th></tr>
            """
            for res in results:
                result_status = res.get(
                    "status", "found" if res.get("found") else "not_found"
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
                platform_name = _html(res.get("platform", "Bilinmiyor"))
                url = _html(res.get("url", ""))
                html_content += f"""
                    <tr>
                        <td>{platform_name}</td>
                        <td><a href="{url}" target="_blank" rel="noopener noreferrer" style="color: #4da6ff;">{url}</a></td>
                        <td class="{status_class}">{status_text}</td>
                    </tr>
                """
            html_content += "</table>"

        if "osint_dork" in data:
            target = _html(data["osint_dork"]["target"])
            dorks = data["osint_dork"]["dorks"]
            
            html_content += f"""
                <h2>Arama Motoru (Dork) OSINT ({target})</h2>
                <p>Aşağıdaki bağlantılara tıklayarak arama motorlarında derinlemesine arama yapabilirsiniz.</p>
                <table>
                    <tr><th>Arama Motoru</th><th>Dork Tipi</th><th>Bağlantı</th></tr>
            """
            for d in dorks:
                engine = _html(d.get("engine", "Bilinmiyor"))
                dork_type = _html(d.get("type", "Bilinmiyor"))
                url = _html(d.get("url", ""))
                html_content += f"""
                    <tr>
                        <td>{engine}</td>
                        <td>{dork_type}</td>
                        <td><a href="{url}" target="_blank" rel="noopener noreferrer" style="color: #4da6ff;">Tıkla ve Ara</a></td>
                    </tr>
                """
            html_content += "</table>"

        if "cleaning" in data:
            items = data["cleaning"]["items"]
            total_size = data["cleaning"]["total_size_bytes"]
            is_dry_run = data["cleaning"].get("is_dry_run", False)
            
            mode_text = "(SİMÜLASYON - Silinmedi)" if is_dry_run else "(SİLİNDİ)"
            
            html_content += f"""
                <h2>Sistem Temizliği {mode_text}</h2>
                <p>Toplam <strong>{len(items)}</strong> öğe, <strong>{total_size / (1024*1024):.2f} MB</strong> alan.</p>
                <table>
                    <tr><th>Tip</th><th>Yol</th><th>Boyut (Bayt)</th></tr>
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
            html_content += "</table>"

        html_content += """
                <div class="footer">
                    Oluşturan: Dijital Ayak İzi Temizleyici & OSINT Aracı
                </div>
            </div>
        </body>
        </html>
        """

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        print_success(f"HTML Raporu kaydedildi: {filepath}")
    except Exception as e:
        print_error(f"HTML raporu kaydedilemedi: {e}")

def generate_report(data: dict, output_path: str, format_type: str = "html") -> None:
    """Belirtilen formatta rapor üretir."""
    if format_type.lower() == "json":
        if not output_path.endswith(".json"):
            output_path += ".json"
        export_to_json(data, output_path)
    else:
        if not output_path.endswith(".html"):
            output_path += ".html"
        export_to_html(data, output_path)
