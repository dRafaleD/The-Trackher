#!/usr/bin/env python3
"""
Trackher command-line interface.

The tool combines local cleanup helpers with evidence-based OSINT checks for
email addresses and usernames.
"""

from __future__ import annotations

import argparse
import platform
import sys

from utils import __version__
from utils.display import (
    console,
    print_dry_run_table,
    print_email_results,
    print_error,
    print_info,
    print_section,
    print_success,
    print_warning,
    show_banner,
)
from utils.helpers import is_valid_email, is_valid_username_query


def positive_int(value: str) -> int:
    """Validate a positive integer for argparse."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("deger en az 1 olmalidir")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="digitalayakizi",
        description=(
            "Trackher\n"
            "    Windows, macOS ve Linux'ta dijital izleri temizler ve\n"
            "    e-posta veya kullanici adi icin dikkatli OSINT taramalari yapar."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ornekler:\n"
            "  %(prog)s --email kullanici@gmail.com\n"
            "  %(prog)s --username kullanici_adi\n"
            "  %(prog)s --clean-all --dry-run\n"
            "  %(prog)s --clean-shell --clean-browser --yes\n"
            "  %(prog)s --shred ~/gizli_belge.pdf --yes\n"
        ),
    )

    osint_group = parser.add_argument_group(
        "OSINT",
        "Yan etkisiz kontroller ve acik web aramalariyla hedefleri inceler.",
    )
    osint_group.add_argument(
        "--email",
        "-e",
        type=str,
        metavar="ADRES",
        help="Taranacak e-posta adresi",
    )
    osint_group.add_argument(
        "--username",
        "-u",
        type=str,
        metavar="KULLANICI_ADI",
        help="Taranacak kullanici adi",
    )
    osint_group.add_argument(
        "--search-dork",
        action="store_true",
        help="Email veya kullanici adi icin arama motoru baglantilari uretir",
    )

    clean_group = parser.add_argument_group(
        "Temizlik Modulleri",
        "Dijital ayak izlerini kategoriye gore veya toplu olarak temizler.",
    )
    clean_group.add_argument(
        "--clean-shell",
        action="store_true",
        help="Terminal ve kabuk gecmislerini temizler",
    )
    clean_group.add_argument(
        "--clean-browser",
        action="store_true",
        help="Tarayici onbellek ve gecmislerini temizler",
    )
    clean_group.add_argument(
        "--clean-system",
        action="store_true",
        help="Sistem izlerini temizler",
    )
    clean_group.add_argument(
        "--clean-all",
        action="store_true",
        help="Tum temizlik modullerini calistirir",
    )

    shred_group = parser.add_argument_group(
        "Guvenli Silme",
        "Dosyanin uzerine yazarak silmeyi dener; SSD/COW sistemlerinde garanti vermez.",
    )
    shred_group.add_argument(
        "--shred",
        "-s",
        type=str,
        metavar="YOL",
        help="Guvenli sekilde silinecek dosya veya dizin yolu",
    )
    shred_group.add_argument(
        "--shred-passes",
        type=positive_int,
        default=3,
        metavar="N",
        help="Uzerine yazma gecis sayisi (varsayilan: 3)",
    )

    general_group = parser.add_argument_group("Genel Secenekler")
    general_group.add_argument(
        "--version",
        action="version",
        version=f"Trackher {__version__}",
        help="Surum bilgisini gosterir ve cikar",
    )
    general_group.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Gercek silme yapmadan neyin silinecegini raporlar",
    )
    general_group.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Etkilesimli onayi atlar",
    )
    general_group.add_argument(
        "--report",
        "-r",
        type=str,
        metavar="FORMAT",
        choices=["html", "json"],
        help="Sonuclari HTML veya JSON olarak raporlar",
    )
    general_group.add_argument(
        "--exclude",
        "-x",
        type=str,
        metavar="CONFIG.JSON",
        help="Belirtilen JSON dosyasindaki yollari temizlikten haric tutar",
    )
    general_group.add_argument(
        "--schedule",
        type=str,
        choices=["daily", "weekly"],
        help="Gunluk veya haftalik zamanlanmis gorev olusturur",
    )
    general_group.add_argument(
        "--setup-context",
        action="store_true",
        help="Windows/Linux sag tik menusune 'Guvenli Sil' secenegi ekler",
    )
    general_group.add_argument(
        "--no-banner",
        action="store_true",
        help="Acilis bannerini gostermez",
    )

    return parser


def confirm_destructive_action(args: argparse.Namespace) -> bool:
    """Ask for confirmation before destructive operations."""
    cleaning = any((args.clean_shell, args.clean_browser, args.clean_system, args.clean_all))
    destructive = not args.dry_run and bool(cleaning or args.shred or args.schedule)
    if not destructive or args.yes:
        return True

    if not sys.stdin.isatty():
        print_error(
            "Kalici islem onaylanmadi. Once --dry-run kullanin veya bilincli "
            "olarak --yes ekleyin."
        )
        return False

    try:
        answer = input("Kalici silme veya zamanlama yapilacak. Devam edilsin mi? [e/H]: ")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False

    if answer.strip().casefold() in {"e", "evet", "y", "yes"}:
        return True
    print_warning("Islem kullanici tarafindan iptal edildi.")
    return False


def handle_email(email: str) -> dict:
    """Run an email OSINT scan."""
    if not is_valid_email(email):
        print_error(f"Gecersiz e-posta formati: {email}")
        sys.exit(1)

    print_section("E-posta OSINT")
    print_info(f"Taraniyor: [bold]{email}[/bold]")
    console.print()

    from osint.checker import run_email_check
    from osint.services import ALL_SERVICES, PASSIVE_SERVICES

    print_info(
        f"E-posta katalogu: [bold]{len(ALL_SERVICES)}[/bold] servis; "
        f"[bold]{len(PASSIVE_SERVICES)}[/bold] yan etkisiz kontrol denenir, "
        f"[bold]{len(ALL_SERVICES) - len(PASSIVE_SERVICES)}[/bold] riskli sorgu atlanir."
    )

    results = run_email_check(email)
    print_email_results(email, results)
    return {"target": email, "results": results}


def handle_username(username: str) -> dict:
    """Run a username OSINT scan."""
    if not is_valid_username_query(username):
        print_error("Kullanici adi 1-100 yazdirilabilir karakter olmali.")
        sys.exit(1)

    print_section("Kullanici Adi OSINT")
    print_info(f"Taraniyor: [bold]{username}[/bold]")
    console.print()

    from osint.username_checker import USERNAME_PLATFORMS, run_username_check
    from utils.display import print_username_results

    print_info(
        f"Kullanici adi listesi: [bold]{len(USERNAME_PLATFORMS)}[/bold] platform taranacak."
    )

    results = run_username_check(username)
    print_username_results(username, results)
    return {"target": username, "results": results}


def handle_dork(target: str) -> dict:
    """Generate search engine dork links."""
    print_section("Arama Motoru Dork Sonuclari")
    from osint.dorking import generate_dorks
    from utils.display import print_dork_results

    dorks = generate_dorks(target)
    print_dork_results(target, dorks)
    return {"target": target, "dorks": dorks}


def handle_cleaning(args: argparse.Namespace) -> dict:
    """Run selected cleanup modules."""
    all_items: list[dict] = []

    clean_shell = args.clean_shell or args.clean_all
    clean_browser = args.clean_browser or args.clean_all
    clean_system = args.clean_system or args.clean_all

    if clean_shell:
        print_section("Kabuk Gecmisi Temizligi")
        from footprint.shell import clean_shell_history

        all_items.extend(clean_shell_history(dry_run=args.dry_run))

    if clean_browser:
        print_section("Tarayici Onbellek Temizligi")
        from footprint.browser import clean_browser_data

        all_items.extend(clean_browser_data(dry_run=args.dry_run))

    if clean_system:
        print_section("Sistem Izleri Temizligi")
        from footprint.system import clean_system_traces

        all_items.extend(clean_system_traces(dry_run=args.dry_run))

    total = sum(item.get("size", 0) for item in all_items)

    if args.dry_run and all_items:
        console.print()
        print_dry_run_table(all_items)
    elif args.dry_run and not all_items:
        print_info("Temizlenecek herhangi bir iz bulunamadi. Sistem zaten temiz gorunuyor.")
    elif all_items:
        from utils.helpers import format_size

        console.print()
        print_success(
            f"Temizlik tamamlandi. [bold]{len(all_items)}[/bold] oge isledi, "
            f"[bold]{format_size(total)}[/bold] alan kazanildi."
        )
    else:
        print_info("Temizlenecek herhangi bir iz bulunamadi. Sistem zaten temiz gorunuyor.")

    return {
        "items": all_items,
        "total_size_bytes": total,
        "is_dry_run": args.dry_run,
    }


def handle_shred(args: argparse.Namespace) -> None:
    """Run secure deletion."""
    print_section("Guvenli Silme")

    from utils.helpers import expand_path

    target = expand_path(args.shred, resolve_symlinks=False)

    if not target.exists():
        print_error(f"Dosya veya dizin bulunamadi: {target}")
        sys.exit(1)

    from footprint.shredder import shred_directory, shred_file

    if target.is_file():
        shred_file(str(target), passes=args.shred_passes, dry_run=args.dry_run)
    elif target.is_dir():
        shred_directory(
            str(target),
            passes=args.shred_passes,
            dry_run=args.dry_run,
            collect_results=False,
        )
    else:
        print_error(f"Desteklenmeyen dosya turu: {target}")


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.email:
        args.email = args.email.strip()
    if args.username:
        args.username = args.username.strip()

    has_action = any(
        [
            args.email,
            args.username,
            args.search_dork,
            args.clean_shell,
            args.clean_browser,
            args.clean_system,
            args.clean_all,
            args.shred,
            args.schedule,
            args.setup_context,
        ]
    )

    if not has_action and len(sys.argv) == 1:
        try:
            import gui

            app = gui.TrackherApp()
            app.mainloop()
            sys.exit(0)
        except ImportError:
            show_banner()
            parser.print_help()
            print_error("\nGUI modulleri yuklenemedi. 'pip install -r requirements.txt' gerekebilir.")
            sys.exit(1)
        except Exception as exc:
            show_banner()
            parser.print_help()
            print_error(f"\nGUI baslatilamadi: {exc}. CLI seceneklerini kullanabilirsiniz.")
            sys.exit(1)

    if not has_action:
        if not args.no_banner:
            show_banner()
        parser.print_help()
        print_error("Bir islem belirtin; ornegin --email, --username veya --clean-all.")
        sys.exit(2)

    if not args.no_banner:
        show_banner()

    if args.dry_run:
        print_warning("Kuru calistirma modu aktif. Hicbir dosya silinmeyecek.\n")

    if args.exclude:
        from utils.helpers import load_exclusions

        try:
            exclusion_count = load_exclusions(args.exclude)
        except (OSError, ValueError) as exc:
            print_error(f"Dislama listesi yuklenemedi: {exc}")
            sys.exit(2)

        print_info(
            f"Dislama listesi yuklendi: {args.exclude} "
            f"({exclusion_count} korunan yol)\n"
        )

    if not confirm_destructive_action(args):
        sys.exit(2)

    report_data: dict[str, dict] = {}

    if args.email:
        report_data["osint_email"] = handle_email(args.email)

    if args.username:
        report_data["osint_username"] = handle_username(args.username)

    if args.search_dork:
        target = args.email or args.username
        if target:
            report_data["osint_dork"] = handle_dork(target)
        else:
            print_warning("Dork aramasi icin --email veya --username belirtmeniz gerekir.")

    if any([args.clean_shell, args.clean_browser, args.clean_system, args.clean_all]):
        report_data["cleaning"] = handle_cleaning(args)

    if args.shred:
        handle_shred(args)

    if args.schedule:
        from utils.scheduler import schedule_task

        print_section("Otomasyon")
        schedule_task(args.schedule, dry_run=args.dry_run)

    if args.setup_context:
        print_section("Sistem Entegrasyonu")
        import setup_context_menu

        if platform.system() == "Windows":
            setup_context_menu.setup_windows_context_menu()
        elif platform.system() == "Linux":
            setup_context_menu.setup_linux_context_menu()
        else:
            print_error("Sag tik menusu entegrasyonu macOS'ta henuz desteklenmiyor.")

    if args.report and report_data:
        from utils.reporter import generate_report

        output_file = f"footprint_report_{args.report}"
        generate_report(report_data, output_file, format_type=args.report)

    console.print()
    print_info("Islem tamamlandi.\n")


if __name__ == "__main__":
    main()
