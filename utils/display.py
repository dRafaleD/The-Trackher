"""
Terminal display helpers for Trackher.

The output stays readable on Windows, macOS, and Linux terminals while using
Rich for tables and section headers.
"""

from __future__ import annotations

import platform
import sys

from rich import box
from rich.console import Console
from rich.table import Table

from utils import __version__


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
 /_____/_/\__, /_/\__/\__,_/_/  /_/  |_|\__, /\__,_/_/|_/_/\__,_/_/_/
         /____/                        /____/
"""


def show_banner() -> None:
    """Print the ASCII banner and runtime details."""
    os_name = platform.system()
    os_ver = platform.release()
    py_ver = platform.python_version()

    console.print(BANNER, style="bold cyan")
    console.print(
        "  [dim]Linux / macOS / Windows - Digital Footprint Cleaner and Email OSINT[/dim]"
    )
    console.print(
        f"  [dim]Trackher | v{__version__} | OS: {os_name} {os_ver} | Python {py_ver}[/dim]\n"
    )


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"  [bold green][OK][/bold green] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"  [bold yellow][WARN][/bold yellow] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"  [bold red][ERR][/bold red] {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"  [bold blue][INFO][/bold blue] {message}")


def print_section(title: str) -> None:
    """Print a highlighted section title."""
    console.print()
    console.rule(f"[bold]{title}[/bold]", style="cyan")
    console.print()


def print_dry_run_table(items: list[dict]) -> None:
    """Render dry-run cleanup results as a table."""
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
    table.add_column("Durum", style="yellow", width=8, justify="center")
    table.add_column("Tur", style="dim", width=18)
    table.add_column("Dosya / Dizin", style="white", ratio=3)
    table.add_column("Boyut", style="green", justify="right", width=12)

    from .helpers import format_size

    total_bytes = 0
    for item in items:
        size = item.get("size", 0)
        total_bytes += size
        table.add_row(
            "SIL",
            item.get("type", "dosya"),
            item.get("path", "-"),
            format_size(size),
        )

    console.print(table)
    console.print(
        f"\n  [bold magenta]Toplam kazanılacak alan:[/bold magenta] "
        f"[bold white]{format_size(total_bytes)}[/bold white]\n"
    )


def print_email_results(email: str, results: list[dict]) -> None:
    """Render email OSINT results as a table."""
    table = Table(
        title=f"E-posta İz Sürücü - {email}",
        box=box.ROUNDED,
        title_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Platform", style="white", ratio=2)
    table.add_column("Durum", width=16, justify="center")
    table.add_column("Detay", style="dim", ratio=3)

    found_count = 0
    unknown_count = 0
    skipped_count = 0
    status_order = {"found": 0, "unknown": 1, "skipped": 2, "not_found": 3}
    sorted_results = sorted(
        results,
        key=lambda item: status_order.get(
            item.get("status", "found" if item.get("found") else "not_found"),
            1,
        ),
    )
    for result in sorted_results:
        result_status = result.get(
            "status", "found" if result.get("found") else "not_found"
        )
        if result_status == "found":
            status = "[bold green]KAYITLI[/bold green]"
            found_count += 1
        elif result_status == "unknown":
            status = "[yellow]DOĞRULANAMADI[/yellow]"
            unknown_count += 1
        elif result_status == "skipped":
            status = "[cyan]ATLANDI[/cyan]"
            skipped_count += 1
        else:
            status = "[dim]bulunamadı[/dim]"
        table.add_row(result["service"], status, result.get("detail", ""))

    console.print(table)
    console.print(
        f"\n  [bold cyan]Toplam:[/bold cyan] "
        f"[bold white]{found_count}[/bold white] doğrulanmış kayıt, "
        f"[bold yellow]{unknown_count}[/bold yellow] sonuç doğrulanamadı, "
        f"[bold cyan]{skipped_count}[/bold cyan] riskli sorgu atlandı "
        f"([dim]{len(results)} katalog öğesi değerlendirildi[/dim]).\n"
    )


def print_username_results(username: str, results: list[dict]) -> None:
    """Render username OSINT results as a table."""
    table = Table(
        title=f"Kullanıcı Adı İz Sürücü - {username}",
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
    for result in sorted_results:
        result_status = result.get(
            "status", "found" if result.get("found") else "not_found"
        )
        if result_status == "found":
            status = "[bold green]KAYITLI[/bold green]"
            found_count += 1
        elif result_status == "unknown":
            status = "[yellow]DOĞRULANAMADI[/yellow]"
            unknown_count += 1
        else:
            status = "[dim]bulunamadı[/dim]"
        table.add_row(result["platform"], status, result.get("url", ""))

    console.print(table)
    console.print(
        f"\n  [bold magenta]Toplam:[/bold magenta] "
        f"[bold white]{found_count}[/bold white] platformda kayıt tespit edildi "
        f"([dim]{len(results)} servis tarandı, {unknown_count} sonuç doğrulanamadı[/dim]).\n"
    )


def print_dork_results(target: str, dorks: list[dict]) -> None:
    """Render search engine dorks as a table."""
    table = Table(
        title=f"Arama Motoru Dork Sonuçları - {target}",
        box=box.ROUNDED,
        title_style="bold yellow",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Arama Motoru", style="white", ratio=1)
    table.add_column("Tur", style="cyan", ratio=2)
    table.add_column("Baglanti", style="blue", ratio=4)

    for dork in dorks:
        table.add_row(dork["engine"], dork["type"], dork["url"])

    console.print(table)
    console.print(
        "\n  [bold yellow][INFO][/bold yellow] Baglantilari tiklayarak veya "
        "tarayıcıya kopyalayarak derin arama yapabilirsiniz.\n"
    )
