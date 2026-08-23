#!/usr/bin/env python3
"""
Trackher command-line interface.

The tool combines local cleanup helpers with cautious username and email OSINT
checks, breach lookups, and search-link generation.
"""

from __future__ import annotations

import argparse
import logging
import platform
import sys
from typing import Any

from utils import __version__
from utils.app_logging import configure_logging, get_logger, safe_log
from utils.display import (
    console,
    print_correlation_summary,
    print_email_results,
    print_dry_run_table,
    print_platform_health_summary,
    print_error,
    print_info,
    print_risk_summary,
    print_remediation_summary,
    print_scan_diff,
    print_section,
    print_success,
    print_warning,
    show_banner,
    show_home_screen,
)
from utils.correlation import build_identity_correlation
from utils.helpers import is_valid_email, is_valid_username_query
from utils.history import clear_scan_history, save_and_diff_scan
from utils.risk import compute_risk
from utils.remediation import build_remediation_report
from utils.profiles import (
    DEFAULT_SCAN_PROFILE,
    PROFILE_ORDER,
    normalize_scan_profile,
    profile_allows_email,
    profile_allows_username,
    profile_description,
    profile_request_policy_description,
)
from utils.platform_health import run_platform_health_check
from utils.runtime import validate_runtime


def positive_int(value: str) -> int:
    """Validate a positive integer for argparse."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="trackher",
        description=(
            "Trackher\n"
            "    Digital footprint and privacy toolkit for Windows, macOS, and Linux.\n"
            "    Provides cleanup, secure deletion, and cautious username/email OSINT."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --email user@example.com\n"
            "  %(prog)s --username username\n"
            "  %(prog)s --profile quick --username username\n"
            "  %(prog)s --profile standard --email user@example.com\n"
            "  %(prog)s --profile deep --username username\n"
            "  %(prog)s --username username --search-dork\n"
            "  %(prog)s --clean-all --dry-run\n"
            "  %(prog)s --clean-shell --clean-browser --yes\n"
            "  %(prog)s --shred ~/private_document.pdf --yes\n"
            "\n"
            "Profiles:\n"
            "  quick        Verified sources; up to 6 concurrent requests; 0.5s/site baseline.\n"
            "  standard     Balanced coverage; up to 4 concurrent requests; 1s/site baseline.\n"
            "  deep         Full coverage; up to 2 concurrent requests; 2s/site baseline;\n"
            "               sensitive sites may use 5-10s/site.\n"
            "  username-only / email-only  Restrict the scan type with standard pacing.\n"
        ),
    )

    osint_group = parser.add_argument_group(
        "OSINT",
        "Investigate targets using public email, username, and web sources.",
    )
    osint_group.add_argument(
        "--email",
        "-e",
        type=str,
        metavar="EMAIL",
        help="Email address to scan",
    )
    osint_group.add_argument(
        "--username",
        "-u",
        type=str,
        metavar="USERNAME",
        help="Username to scan",
    )
    osint_group.add_argument(
        "--search-dork",
        action="store_true",
        help="Generate search-engine links for an email or username",
    )
    osint_group.add_argument(
        "--show-manual",
        action="store_true",
        help="Show services that require manual email investigation",
    )
    osint_group.add_argument(
        "--show-actions",
        action="store_true",
        help="Show detailed remediation and privacy action links",
    )
    osint_group.add_argument(
        "--profile",
        type=str,
        choices=list(PROFILE_ORDER),
        default=DEFAULT_SCAN_PROFILE,
        help="Choose a scan profile: quick, standard, deep, username-only, or email-only",
    )
    osint_group.add_argument(
        "--health-check",
        action="store_true",
        help="Check platform and detector health using schema checks",
    )
    osint_group.add_argument(
        "--health-check-live",
        action="store_true",
        help="Also run safe live probes during the platform health check",
    )

    clean_group = parser.add_argument_group(
        "Cleanup Modules",
        "Clean digital footprint artifacts by category or as a complete set.",
    )
    clean_group.add_argument(
        "--clean-shell",
        action="store_true",
        help="Clean terminal and shell history",
    )
    clean_group.add_argument(
        "--clean-browser",
        action="store_true",
        help="Clean browser cache and history",
    )
    clean_group.add_argument(
        "--clean-system",
        action="store_true",
        help="Clean system artifacts",
    )
    clean_group.add_argument(
        "--clean-all",
        action="store_true",
        help="Run all cleanup modules",
    )

    shred_group = parser.add_argument_group(
        "Secure Deletion",
        "Attempt overwrite-based deletion; this cannot guarantee removal on SSD/COW filesystems.",
    )
    shred_group.add_argument(
        "--shred",
        "-s",
        type=str,
        metavar="PATH",
        help="File or directory path to securely delete",
    )
    shred_group.add_argument(
        "--shred-passes",
        type=positive_int,
        default=3,
        metavar="N",
        help="Number of overwrite passes (default: 3)",
    )

    general_group = parser.add_argument_group("General Options")
    general_group.add_argument(
        "--version",
        action="version",
        version=f"Trackher {__version__}",
        help="Show the version and exit",
    )
    general_group.add_argument(
        "--dry-run",
        "-d",
        action="store_true",
        help="Report what would be deleted without making changes",
    )
    general_group.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip interactive confirmation",
    )
    general_group.add_argument(
        "--report",
        "-r",
        type=str,
        metavar="FORMAT",
        choices=["html", "json"],
        help="Write results as HTML or JSON",
    )
    general_group.add_argument(
        "--exclude",
        "-x",
        type=str,
        metavar="CONFIG.JSON",
        help="Exclude paths listed in the specified JSON file from cleanup",
    )
    general_group.add_argument(
        "--schedule",
        type=str,
        choices=["daily", "weekly"],
        help="Create a daily or weekly scheduled task",
    )
    general_group.add_argument(
        "--setup-context",
        action="store_true",
        help="Add a 'Secure Delete' context-menu entry on Windows/Linux",
    )
    general_group.add_argument(
        "--gui",
        action="store_true",
        help="Launch the graphical interface",
    )
    general_group.add_argument(
        "--no-banner",
        action="store_true",
        help="Hide the startup banner",
    )
    general_group.add_argument(
        "--no-history",
        action="store_true",
        help="Disable local scan history and diff comparisons",
    )
    general_group.add_argument(
        "--clear-history",
        action="store_true",
        help="Safely clear local scan history",
    )

    return parser


def confirm_destructive_action(args: argparse.Namespace) -> bool:
    """Ask for confirmation before destructive operations."""
    cleaning = any((args.clean_shell, args.clean_browser, args.clean_system, args.clean_all))
    destructive = not args.dry_run and bool(
        cleaning or args.shred or args.schedule or args.clear_history
    )
    if not destructive or args.yes:
        return True

    if not sys.stdin.isatty():
        print_error("Permanent operation not confirmed. Use --dry-run first or explicitly add --yes.")
        return False

    try:
        answer = input("Permanent deletion or scheduling will be performed. Continue? [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False

    if answer.strip().casefold() in {"y", "yes"}:
        return True
    print_warning("Operation cancelled by the user.")
    return False


def handle_email(email: str, *, show_manual: bool = False, profile: str = DEFAULT_SCAN_PROFILE) -> dict:
    """Run an email OSINT scan."""
    if not is_valid_email(email):
        print_error(f"Invalid email format: {email}")
        sys.exit(1)

    print_section("Email OSINT")
    print_info(f"Scanning: [bold]{email}[/bold]")
    console.print()

    from osint.checker import run_email_check
    from osint.services import ACCOUNT_PLATFORMS, BREACH_PLATFORMS
    from utils.profiles import select_email_platforms

    account_platforms, breach_platforms = select_email_platforms(
        profile,
        ACCOUNT_PLATFORMS,
        BREACH_PLATFORMS,
    )
    print_info(
        f"Profil: [bold]{profile}[/bold] - {profile_description(profile)}"
    )
    print_info(f"Ag politikasi: {profile_request_policy_description(profile)}")
    print_info(
        f"Email catalog: [bold]{len(account_platforms)}[/bold] account services; "
        f"[bold]{sum(1 for item in account_platforms if item.get('check', 'manual') != 'manual')}[/bold] "
        "side-effect-free automatic detectors; "
        f"[bold]{len(breach_platforms)}[/bold] breach providers; "
        f"[bold]{len(ACCOUNT_PLATFORMS) - len(account_platforms)}[/bold] account services excluded."
    )

    results = run_email_check(email, profile=profile)
    print_email_results(email, results, show_manual=show_manual)
    return {"target": email, "results": results}


def handle_username(username: str, *, profile: str = DEFAULT_SCAN_PROFILE) -> dict:
    """Run a username OSINT scan."""
    if is_valid_email(username):
        print_error("This input looks like an email address. Use --email instead.")
        sys.exit(1)
    if not is_valid_username_query(username):
        print_error("Username must contain 1-100 printable characters.")
        sys.exit(1)

    print_section("Username OSINT")
    print_info(f"Scanning: [bold]{username}[/bold]")
    console.print()

    from osint.username_checker import USERNAME_PLATFORMS, run_username_check
    from utils.display import print_username_results
    from utils.profiles import select_username_platforms

    selected_platforms = select_username_platforms(profile, USERNAME_PLATFORMS)
    print_info(f"Profil: [bold]{profile}[/bold] - {profile_description(profile)}")
    print_info(f"Ag politikasi: {profile_request_policy_description(profile)}")
    print_info(
        f"Username catalog: [bold]{len(selected_platforms)}[/bold] platforms selected; "
        f"[bold]{len(USERNAME_PLATFORMS) - len(selected_platforms)}[/bold] platforms excluded."
    )

    results = run_username_check(username, profile=profile)
    print_username_results(username, results)
    return {"target": username, "results": results}


def handle_dork(target: str) -> dict:
    """Generate search engine dork links."""
    print_section("Search Dork Results")
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
        print_section("Shell History Cleanup")
        from footprint.shell import clean_shell_history

        all_items.extend(clean_shell_history(dry_run=args.dry_run))

    if clean_browser:
        print_section("Browser Cache Cleanup")
        from footprint.browser import clean_browser_data

        all_items.extend(clean_browser_data(dry_run=args.dry_run))

    if clean_system:
        print_section("System Artifact Cleanup")
        from footprint.system import clean_system_traces

        all_items.extend(clean_system_traces(dry_run=args.dry_run))

    total = sum(item.get("size", 0) for item in all_items)

    if args.dry_run and all_items:
        console.print()
        print_dry_run_table(all_items)
    elif args.dry_run and not all_items:
        print_info("No artifacts found to clean. The system already appears clean.")
    elif all_items:
        from utils.helpers import format_size

        console.print()
        print_success(
            f"Cleanup complete. Processed [bold]{len(all_items)}[/bold] items and reclaimed "
            f"[bold]{format_size(total)}[/bold]."
        )
    else:
        print_info("No artifacts found to clean. The system already appears clean.")

    return {
        "items": all_items,
        "total_size_bytes": total,
        "is_dry_run": args.dry_run,
    }


def handle_shred(args: argparse.Namespace) -> None:
    """Run secure deletion."""
    print_section("Secure Deletion")

    from utils.helpers import expand_path

    target = expand_path(args.shred, resolve_symlinks=False)

    if not target.exists():
        print_error(f"File or directory not found: {target}")
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
        print_error(f"Unsupported file type: {target}")


def launch_gui(logger: logging.Logger, parser: argparse.ArgumentParser) -> None:
    """Launch the existing GUI as an explicit mode."""
    try:
        import gui

        app = gui.TrackherApp()
        app.mainloop()
    except ImportError:
        safe_log(logger, logging.ERROR, "GUI import failed")
        show_banner()
        parser.print_help()
        print_error("\nGUI modules could not be loaded. You may need to install requirements.txt.")
        sys.exit(1)
    except Exception as exc:
        safe_log(logger, logging.ERROR, "GUI startup failed: %s", exc)
        show_banner()
        parser.print_help()
        print_error(f"\nGUI could not start: {exc}. You can use the CLI options instead.")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    configure_logging()
    logger = get_logger("cli")
    parser = build_parser()
    args = parser.parse_args()

    if args.email:
        args.email = args.email.strip()
    if args.username:
        args.username = args.username.strip()

    if len(sys.argv) == 1:
        show_home_screen()
        sys.exit(0)

    if args.gui:
        launch_gui(logger, parser)
        sys.exit(0)

    has_action = any(
        [
            args.email,
            args.username,
            args.search_dork,
            args.health_check,
            args.health_check_live,
            args.clean_shell,
            args.clean_browser,
            args.clean_system,
            args.clean_all,
            args.shred,
            args.schedule,
            args.setup_context,
            args.clear_history,
        ]
    )

    if not has_action:
        if not args.no_banner:
            show_banner()
        parser.print_help()
        print_error("Specify an operation, for example --email, --username, or --clean-all.")
        sys.exit(2)

    scan_profile = normalize_scan_profile(args.profile)
    runtime_state = validate_runtime()
    for warning in runtime_state.get("warnings", []):
        print_warning(str(warning))
    if runtime_state.get("warnings"):
        safe_log(logger, logging.WARNING, "Runtime validation warnings: %s", runtime_state.get("warnings"))

    if not args.no_banner:
        show_banner()
        print_info(
            f"Scan profile selected: [bold]{scan_profile}[/bold] - "
            f"{profile_description(scan_profile)}"
        )

    if args.dry_run:
        print_warning("Dry-run mode is active. No files will be deleted.\n")

    if args.exclude:
        from utils.helpers import load_exclusions

        try:
            exclusion_count = load_exclusions(args.exclude)
        except (OSError, ValueError) as exc:
            print_error(f"Exclusion list could not be loaded: {exc}")
            sys.exit(2)

        print_info(
            f"Exclusion list loaded: {args.exclude} "
            f"({exclusion_count} protected paths)\n"
        )

    if not confirm_destructive_action(args):
        sys.exit(2)

    if args.clear_history:
        cleared = clear_scan_history()
        print_section("Scan History")
        print_success(
            f"Local scan history cleared: {cleared['removed_files']} items removed."
        )
        if not any([args.email, args.username, args.search_dork, args.clean_shell, args.clean_browser, args.clean_system, args.clean_all, args.shred, args.schedule, args.setup_context]):
            console.print()
            print_info("Operation complete.\n")
            sys.exit(0)

    report_data: dict[str, Any] = {}
    report_data["scan_profile"] = scan_profile

    if args.health_check or args.health_check_live:
        print_section("Platform Health")
        report_data["platform_health"] = run_platform_health_check(live=args.health_check_live)
        print_platform_health_summary(report_data["platform_health"])

    run_email_scan = bool(args.email) and profile_allows_email(scan_profile)
    run_username_scan = bool(args.username) and profile_allows_username(scan_profile)

    if args.email and not run_email_scan:
        print_warning("Selected profile does not include email scans; skipping --email input.")
    if args.username and not run_username_scan:
        print_warning("Selected profile does not include username scans; skipping --username input.")

    if (
        not run_email_scan
        and not run_username_scan
        and not any(
            [
                args.search_dork,
                args.health_check,
                args.health_check_live,
                args.clean_shell,
                args.clean_browser,
                args.clean_system,
                args.clean_all,
                args.shred,
                args.schedule,
                args.setup_context,
                args.clear_history,
            ]
        )
    ):
        print_warning("Selected profile did not enable any requested OSINT scans.")
        sys.exit(2)

    if run_email_scan:
        report_data["osint_email"] = handle_email(
            args.email,
            show_manual=args.show_manual,
            profile=scan_profile,
        )

    if run_username_scan:
        report_data["osint_username"] = handle_username(args.username, profile=scan_profile)

    if args.search_dork:
        target = args.email or args.username
        if target:
            report_data["osint_dork"] = handle_dork(target)
        else:
            print_warning("Specify --email or --username to generate search dorks.")

    if any([args.clean_shell, args.clean_browser, args.clean_system, args.clean_all]):
        report_data["cleaning"] = handle_cleaning(args)

    if args.shred:
        handle_shred(args)

    if args.schedule:
        from utils.scheduler import schedule_task

        print_section("Otomasyon")
        schedule_task(args.schedule, dry_run=args.dry_run)

    if args.setup_context:
        print_section("System Integration")
        import setup_context_menu

        if platform.system() == "Windows":
            setup_context_menu.setup_windows_context_menu()
        elif platform.system() == "Linux":
            setup_context_menu.setup_linux_context_menu()
        else:
            print_error("Context-menu integration is not supported on macOS yet.")

    if any(key in report_data for key in ("osint_email", "osint_username")):
        report_data["risk"] = compute_risk(report_data)
        print_section("Risk Score")
        print_risk_summary(report_data["risk"])
        report_data["scan_history"] = save_and_diff_scan(report_data, enabled=not args.no_history)
        print_section("Scan Diff")
        print_scan_diff(report_data["scan_history"])
        report_data["correlation"] = build_identity_correlation(report_data)
        if report_data["correlation"].get("available"):
            print_section("Identity Correlation")
            print_correlation_summary(report_data["correlation"])
        report_data["remediation"] = build_remediation_report(report_data)
        if report_data["remediation"].get("available"):
            print_section("Remediation / Privacy Actions")
            print_remediation_summary(report_data["remediation"], show_details=args.show_actions)

    if args.report and any(
        key in report_data
        for key in ("osint_email", "osint_username", "osint_dork", "cleaning", "platform_health")
    ):
        from utils.reporter import generate_report

        output_file = f"trackher_report_{args.report}"
        generate_report(report_data, output_file, format_type=args.report)

    console.print()
    print_info("Operation complete.\n")


if __name__ == "__main__":
    main()
