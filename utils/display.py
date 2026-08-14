"""
Dijital Ayak İzi Temizleyici — Terminal Görüntüleme Araçları

Rich kütüphanesi ile renkli, tablolu ve ikonlu terminal çıktıları üretir.
"""

import sys

from rich.console import Console
from rich.table import Table
from rich import box


for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

console = Console()

BANNER = r"""
     ____  _       _ __        __   ___              __   __     _
    / __ \(_)___ _(_) /_____ _/ /  /   |  __  _____ _/ /__/ /_  (_)___(_)
   / / / / / __ `/ / __/ __ `/ /  / /| | / / / / __ `/ //_/ / / / /_/ /
  / /_/ / / /_/ / / /_/ /_/ / /  / ___ |/ /_/ / /_/ / ,< / / /_/ / / /
 /_____/_/\__, /_/\__/\__,_/_/  /_/  |_|\__, /\__,_/_/|_/_/\__,_/ /_/
         /____/                        /____/
"""


def show_banner() -> None:
    """ASCII logosunu ve proje bilgilerini ekrana basar."""
    import platform
    os_name = platform.system()
    os_ver  = platform.release()
    py_ver  = platform.python_version()

    console.print(BANNER, style="bold cyan")
    console.print(
        "  [dim]Linux · macOS · Windows — Dijital Ayak İzi Temizleyici & E-posta OSINT Aracı[/dim]"
    )
    console.print(
        f"  [dim]github.com/digitalayakizi  •  v1.1.0  •  "
        f"OS: {os_name} {os_ver}  •  Python {py_ver}[/dim]\n"
    )


def print_success(message: str) -> None:
    """Başarılı işlem mesajı basar."""
    console.print(f"  [bold green]✔[/bold green]  {message}")


def print_warning(message: str) -> None:
    """Uyarı mesajı basar."""
    console.print(f"  [bold yellow]⚠[/bold yellow]  {message}")


def print_error(message: str) -> None:
    """Hata mesajı basar."""
    console.print(f"  [bold red]✘[/bold red]  {message}")


def print_info(message: str) -> None:
    """Bilgi mesajı basar."""
    console.print(f"  [bold blue]ℹ[/bold blue]  {message}")


def print_section(title: str) -> None:
    """Modül başlığını vurgulu bir şekilde basar."""
    console.print()
    console.rule(f"[bold]{title}[/bold]", style="cyan")
    console.print()


def print_dry_run_table(items: list[dict]) -> None:
    """
    Dry-run sonuçlarını tablo olarak basar.

    Her item dict: {"path": str, "size": int, "type": str}
    """
    if not items:
        print_info("Temizlenecek dosya bulunamadı.")
        return

    table = Table(
        title="Kuru Çalıştırma (Dry-Run) Raporu",
        box=box.ROUNDED,
        title_style="bold magenta",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Durum", style="yellow", width=6, justify="center")
    table.add_column("Tür", style="dim", width=12)
    table.add_column("Dosya / Dizin", style="white", ratio=3)
    table.add_column("Boyut", style="green", justify="right", width=12)

    from .helpers import format_size

    total_bytes = 0
    for item in items:
        size = item.get("size", 0)
        total_bytes += size
        table.add_row(
            "SİL",
            item.get("type", "dosya"),
            item.get("path", "—"),
            format_size(size),
        )

    console.print(table)
    console.print(
        f"\n  [bold magenta]Toplam kazanılacak alan:[/bold magenta] "
        f"[bold white]{format_size(total_bytes)}[/bold white]\n"
    )


def print_email_results(email: str, results: list[dict]) -> None:
    """
    E-posta OSINT sonuçlarını tablo olarak basar.

    Her result dict: {"service": str, "found": bool, "detail": str}
    """
    table = Table(
        title=f"E-posta İz Sürücü — {email}",
        box=box.ROUNDED,
        title_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Platform", style="white", ratio=2)
    table.add_column("Durum", width=14, justify="center")
    table.add_column("Detay", style="dim", ratio=3)

    found_count = 0
    for r in sorted(results, key=lambda x: not x["found"]):
        if r["found"]:
            status = "[bold green]KAYITLI ✔[/bold green]"
            found_count += 1
        else:
            status = "[dim]bulunamadı[/dim]"
        table.add_row(r["service"], status, r.get("detail", ""))

    console.print(table)
    console.print(
        f"\n  [bold cyan]Toplam:[/bold cyan] "
        f"[bold white]{found_count}[/bold white] platformda kayıt tespit edildi "
        f"([dim]{len(results)} servis tarandı[/dim]).\n"
    )

def print_username_results(username: str, results: list[dict]) -> None:
    """Kullanıcı adı OSINT sonuçlarını tablo olarak basar."""
    table = Table(
        title=f"Kullanıcı Adı İz Sürücü — {username}",
        box=box.ROUNDED,
        title_style="bold magenta",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Platform", style="white", ratio=2)
    table.add_column("Durum", width=16, justify="center")
    table.add_column("URL", style="blue", ratio=3)

    found_count = 0
    unknown_count = 0
    status_order = {"found": 0, "unknown": 1, "not_found": 2}
    sorted_results = sorted(
        results,
        key=lambda item: status_order.get(
            item.get("status", "found" if item.get("found") else "not_found"),
            1,
        ),
    )
    for r in sorted_results:
        result_status = r.get("status", "found" if r.get("found") else "not_found")
        if result_status == "found":
            status = "[bold green]KAYITLI ✔[/bold green]"
            found_count += 1
        elif result_status == "unknown":
            status = "[yellow]DOĞRULANAMADI[/yellow]"
            unknown_count += 1
        else:
            status = "[dim]bulunamadı[/dim]"
        table.add_row(r["platform"], status, r.get("url", ""))

    console.print(table)
    console.print(
        f"\n  [bold magenta]Toplam:[/bold magenta] "
        f"[bold white]{found_count}[/bold white] platformda kayıt tespit edildi "
        f"([dim]{len(results)} servis tarandı, {unknown_count} sonuç doğrulanamadı[/dim]).\n"
    )


def print_dork_results(target: str, dorks: list[dict]) -> None:
    """Dorking sonuçlarını tablo olarak basar."""
    table = Table(
        title=f"Arama Motoru (Dork) İz Sürücü — {target}",
        box=box.ROUNDED,
        title_style="bold yellow",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Arama Motoru", style="white", ratio=1)
    table.add_column("Tür", style="cyan", ratio=2)
    table.add_column("Arama Bağlantısı (URL)", style="blue", ratio=4)

    for d in dorks:
        table.add_row(d["engine"], d["type"], d["url"])

    console.print(table)
    console.print(
        "\n  [bold yellow]ℹ[/bold yellow]  Yukarıdaki bağlantılara tıklayarak veya tarayıcıya "
        "kopyalayarak derinlemesine arama yapabilirsiniz.\n"
    )
