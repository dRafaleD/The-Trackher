#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dijital Ayak İzi Temizleyici & E-posta OSINT Aracı

Linux sistemlerinde kullanıcının dijital ayak izlerini temizleyen
ve e-posta adreslerinin hangi platformlarda kayıtlı olduğunu tespit eden
modüler bir CLI aracı.

Kullanım:
    python main.py --help
    python main.py --email ornek@domain.com
    python main.py --clean-all
    python main.py --clean-shell --dry-run
    python main.py --shred /path/to/secret.txt
"""

from __future__ import annotations

import argparse
import sys
import platform

from utils.display import (
    console,
    show_banner,
    print_section,
    print_success,
    print_warning,
    print_error,
    print_info,
    print_dry_run_table,
    print_email_results,
)
from utils.helpers import is_valid_email


def positive_int(value: str) -> int:
    """Argparse için sıfırdan büyük tam sayı doğrulayıcısı."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("değer en az 1 olmalıdır")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """CLI argüman ayrıştırıcısını oluşturur."""
    parser = argparse.ArgumentParser(
        prog="digitalayakizi",
        description=(
            "🛡️  Dijital Ayak İzi Temizleyici & E-posta OSINT Aracı\n"
            "    Linux sistemlerinde dijital izlerinizi temizleyin ve\n"
            "    e-posta adreslerinizin kayıtlı olduğu platformları tespit edin."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Örnekler:\n"
            "  %(prog)s --email kullanici@gmail.com\n"
            "  %(prog)s --username kullanici_adi\n"
            "  %(prog)s --clean-all --dry-run\n"
            "  %(prog)s --clean-shell --clean-browser\n"
            "  %(prog)s --shred ~/gizli_belge.pdf\n"
        ),
    )

    # ── E-posta OSINT ─────────────────────────────────────────────
    osint_group = parser.add_argument_group(
        "E-posta İz Sürücü (OSINT)",
        "Girilen e-posta adresinin hangi platformlarda kayıtlı olduğunu tespit eder.",
    )
    osint_group.add_argument(
        "--email", "-e",
        type=str,
        metavar="ADRES",
        help="Taranacak e-posta adresi (örn: user@gmail.com)",
    )
    osint_group.add_argument(
        "--username", "-u",
        type=str,
        metavar="KULLANICI_ADI",
        help="Taranacak kullanıcı adı (örn: john_doe)",
    )
    osint_group.add_argument(
        "--search-dork",
        action="store_true",
        help="Girilen email veya kullanıcı adı için arama motoru (Dork) linkleri üretir",
    )

    # ── Temizlik Modülleri ────────────────────────────────────────
    clean_group = parser.add_argument_group(
        "Temizlik Modülleri",
        "Dijital ayak izlerini kategoriye göre veya toplu olarak temizler.",
    )
    clean_group.add_argument(
        "--clean-shell",
        action="store_true",
        help="Terminal ve kabuk geçmişlerini temizler (bash, zsh, python, vim vb.)",
    )
    clean_group.add_argument(
        "--clean-browser",
        action="store_true",
        help="Tarayıcı önbellek ve geçmişlerini temizler (Firefox, Chrome, Brave)",
    )
    clean_group.add_argument(
        "--clean-system",
        action="store_true",
        help="Sistem izlerini temizler (cache, tmp, trash, recently-used)",
    )
    clean_group.add_argument(
        "--clean-all",
        action="store_true",
        help="Tüm temizlik modüllerini çalıştırır (shell + browser + system)",
    )

    # ── Güvenli Silme ─────────────────────────────────────────────
    shred_group = parser.add_argument_group(
        "Güvenli Silme (Shred)",
        "Dosya veya dizini geri getirilemez şekilde imha eder.",
    )
    shred_group.add_argument(
        "--shred", "-s",
        type=str,
        metavar="YOL",
        help="Güvenli şekilde silinecek dosya veya dizin yolu",
    )
    shred_group.add_argument(
        "--shred-passes",
        type=positive_int,
        default=3,
        metavar="N",
        help="Üzerine yazma geçiş sayısı (varsayılan: 3)",
    )

    # ── Genel Bayraklar ───────────────────────────────────────────
    general_group = parser.add_argument_group("Genel Seçenekler")
    general_group.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Gerçek silme yapmadan neyin silineceğini raporlar",
    )
    general_group.add_argument(
        "--report", "-r",
        type=str,
        metavar="FORMAT",
        choices=["html", "json"],
        help="Sonuçları HTML veya JSON formatında raporlar",
    )
    general_group.add_argument(
        "--exclude", "-x",
        type=str,
        metavar="CONFIG.JSON",
        help="Belirtilen JSON dosyasındaki yolları temizlikten hariç tutar (Whitelist)",
    )
    general_group.add_argument(
        "--schedule",
        type=str,
        choices=["daily", "weekly"],
        help="Sistemi günlük veya haftalık temizlemek için zamanlanmış görev oluşturur",
    )
    general_group.add_argument(
        "--setup-context",
        action="store_true",
        help="İşletim sistemi sağ tık menüsüne 'Güvenli Sil' seçeneğini ekler",
    )
    general_group.add_argument(
        "--no-banner",
        action="store_true",
        help="Açılış bannerını göstermez",
    )

    return parser


def handle_email(email: str) -> dict:
    """E-posta OSINT taramasını çalıştırır."""
    if not is_valid_email(email):
        print_error(f"Geçersiz e-posta formatı: {email}")
        sys.exit(1)

    print_section("E-posta İz Sürücü (OSINT)")
    print_info(f"Taranıyor: [bold]{email}[/bold]")
    console.print()

    from osint.checker import run_email_check
    from osint.services import ALL_SERVICES

    print_info(f"E-posta listesi: [bold]{len(ALL_SERVICES)}[/bold] servis taranacak.")

    results = run_email_check(email)
    print_email_results(email, results)
    
    return {"target": email, "results": results}

def handle_username(username: str) -> dict:
    """Kullanıcı adı OSINT taramasını çalıştırır."""
    print_section("Kullanıcı Adı İz Sürücü (OSINT)")
    print_info(f"Taranıyor: [bold]{username}[/bold]")
    console.print()

    from osint.username_checker import USERNAME_PLATFORMS, run_username_check
    from utils.display import print_username_results

    print_info(
        f"Kullanıcı adı listesi: [bold]{len(USERNAME_PLATFORMS)}[/bold] platform taranacak."
    )

    results = run_username_check(username)
    print_username_results(username, results)
    
    return {"target": username, "results": results}

def handle_dork(target: str) -> dict:
    """Dork bağlantılarını üretir ve gösterir."""
    print_section("Arama Motoru OSINT (Dorking)")
    from osint.dorking import generate_dorks
    from utils.display import print_dork_results
    
    dorks = generate_dorks(target)
    print_dork_results(target, dorks)
    
    return {"target": target, "dorks": dorks}


def handle_cleaning(args: argparse.Namespace) -> dict:
    """Temizlik modüllerini çalıştırır."""
    all_items: list[dict] = []

    clean_shell = args.clean_shell or args.clean_all
    clean_browser = args.clean_browser or args.clean_all
    clean_system = args.clean_system or args.clean_all

    if clean_shell:
        print_section("Kabuk Geçmişi Temizliği")
        from footprint.shell import clean_shell_history
        items = clean_shell_history(dry_run=args.dry_run)
        all_items.extend(items)

    if clean_browser:
        print_section("Tarayıcı Önbellek Temizliği")
        from footprint.browser import clean_browser_data
        items = clean_browser_data(dry_run=args.dry_run)
        all_items.extend(items)

    if clean_system:
        print_section("Sistem İzleri Temizliği")
        from footprint.system import clean_system_traces
        items = clean_system_traces(dry_run=args.dry_run)
        all_items.extend(items)

    total = sum(item.get("size", 0) for item in all_items)
    
    if args.dry_run and all_items:
        console.print()
        print_dry_run_table(all_items)
    elif args.dry_run and not all_items:
        print_info("Temizlenecek herhangi bir iz bulunamadı. Sisteminiz zaten temiz!")
    elif all_items:
        from utils.helpers import format_size
        console.print()
        print_success(
            f"Temizlik tamamlandı! [bold]{len(all_items)}[/bold] öğe silindi, "
            f"[bold]{format_size(total)}[/bold] alan kazanıldı."
        )
    else:
        print_info("Temizlenecek herhangi bir iz bulunamadı. Sisteminiz zaten temiz!")
        
    return {
        "items": all_items,
        "total_size_bytes": total,
        "is_dry_run": args.dry_run
    }


def handle_shred(args: argparse.Namespace) -> None:
    """Güvenli silme işlemini çalıştırır."""
    print_section("Güvenli Silme (Shred)")

    from utils.helpers import expand_path

    target = expand_path(args.shred)

    if not target.exists():
        print_error(f"Dosya veya dizin bulunamadı: {target}")
        sys.exit(1)

    from footprint.shredder import shred_file, shred_directory

    if target.is_file():
        shred_file(str(target), passes=args.shred_passes, dry_run=args.dry_run)
    elif target.is_dir():
        shred_directory(str(target), passes=args.shred_passes, dry_run=args.dry_run)
    else:
        print_error(f"Desteklenmeyen dosya türü: {target}")


def main() -> None:
    """Ana giriş noktası."""
    parser = build_parser()
    args = parser.parse_args()

    # Hiçbir argüman verilmemişse yardım göster
    has_action = any([
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
    ])

    if not has_action:
        # Hiçbir argüman verilmediyse GUI'yi başlat
        try:
            import gui
            app = gui.TrackherApp()
            app.mainloop()
            sys.exit(0)
        except ImportError:
            show_banner()
            parser.print_help()
            print_error("\nGUI modülleri yüklenemedi. ('pip install customtkinter' gerekebilir)")
            sys.exit(0)

    if not args.no_banner:
        show_banner()

    # Dry-run uyarısı
    if args.dry_run:
        print_warning(
            "Kuru çalıştırma modu aktif — hiçbir dosya silinmeyecek.\n"
        )
        
    if args.exclude:
        from utils.helpers import load_exclusions
        try:
            exclusion_count = load_exclusions(args.exclude)
        except (OSError, ValueError) as exc:
            print_error(f"Dışlama listesi yüklenemedi: {exc}")
            sys.exit(2)

        print_info(
            f"Dışlama listesi yüklendi: {args.exclude} "
            f"({exclusion_count} korunan yol)\n"
        )

    report_data = {}

    # İşlemleri çalıştır
    if args.email:
        report_data["osint_email"] = handle_email(args.email)
        
    if args.username:
        report_data["osint_username"] = handle_username(args.username)
        
    if args.search_dork:
        target = args.email or args.username
        if target:
            report_data["osint_dork"] = handle_dork(target)
        else:
            print_warning("Dork araması için --email veya --username belirtmeniz gerekir.")

    if any([args.clean_shell, args.clean_browser, args.clean_system, args.clean_all]):
        report_data["cleaning"] = handle_cleaning(args)

    if args.shred:
        handle_shred(args)

    if args.schedule:
        from utils.scheduler import schedule_task
        print_section("Otomasyon (Görev Zamanlayıcı)")
        schedule_task(args.schedule)

    if args.setup_context:
        print_section("Sistem Entegrasyonu (Sağ Tık Menüsü)")
        import setup_context_menu
        if platform.system() == "Windows":
            setup_context_menu.setup_windows_context_menu()
        elif platform.system() == "Linux":
            setup_context_menu.setup_linux_context_menu()
        else:
            print_error("Bu sistemde desteklenmiyor.")

    if args.report and report_data:
        from utils.reporter import generate_report
        output_file = f"footprint_report_{args.report}"
        generate_report(report_data, output_file, format_type=args.report)

    console.print()
    print_info("İşlem tamamlandı.\n")


if __name__ == "__main__":
    main()
