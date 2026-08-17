"""
Terminal display helpers for Trackher.

The output stays readable on Windows, macOS, and Linux terminals while using
Rich for tables and section headers.
"""

from __future__ import annotations

import json
import platform
import sys
from collections import Counter
from pathlib import Path

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

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
 _______ ____      _     ____ _  ____ _   _ _____ ____
|_   _|  _ \    / \   / ___| |/ /| | | | ____|  _ \
  | | | |_) |  / _ \ | |   | ' / | |_| |  _| | |_) |
  | | |  _ <  / ___ \| |___| . \ |  _  | |___|  _ <
  |_| |_| \_\/_/   \_\\____|_|\_\|_| |_|_____|_| \_\
"""

HOME_EXAMPLES = (
    "trackher --username <username>",
    "trackher --email <email>",
    "trackher --profile deep --username <username>",
    "trackher --health-check",
    "trackher --gui",
    "trackher --help",
)

USERNAME_UNKNOWN_CAUSE_LABELS = {
    "bot_blocked": "bot blocked",
    "parser_mismatch": "parser mismatch",
    "network_error": "network error",
    "forbidden": "forbidden",
    "rate_limited": "rate limited",
    "timeout": "timeout",
    "unexpected_status": "unexpected response",
    "unknown": "unknown",
}

USERNAME_UNKNOWN_CAUSE_ORDER = (
    "bot_blocked",
    "parser_mismatch",
    "network_error",
    "forbidden",
    "rate_limited",
    "timeout",
    "unexpected_status",
    "unknown",
)


def show_banner() -> None:
    """Print the ASCII banner and runtime details."""
    os_name = platform.system()
    os_ver = platform.release()
    py_ver = platform.python_version()

    console.print(BANNER, style="bold cyan")
    console.print("  [bold white]TRACKHER[/bold white]")
    console.print(
        "  [dim]Digital Footprint & Privacy Toolkit[/dim]"
    )
    console.print(
        f"  [dim]Trackher | v{__version__} | OS: {os_name} {os_ver} | Python {py_ver}[/dim]\n"
    )


def _catalog_count(path: Path) -> int | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return len(data) if isinstance(data, list) else None


def _home_catalog_counts() -> tuple[str, str]:
    project_root = Path(__file__).resolve().parent.parent
    username_count = _catalog_count(project_root / "osint" / "platforms.json")
    email_count = _catalog_count(project_root / "osint" / "email_platforms.json")
    return str(username_count or "?"), str(email_count or "?")


def _home_wordmark() -> Text:
    text = Text()
    text.append(BANNER.strip("\n"), style="bold cyan")
    text.append("\n")
    text.append("Digital Footprint & Privacy Toolkit\n", style="white")
    text.append(f"Trackher v{__version__}\n", style="dim")
    return text


def _home_features(username_count: str, email_count: str) -> Text:
    lines = [
        f"[bold cyan][U][/bold cyan] Username Intelligence  [dim]-[/dim] {username_count} platforms",
        f"[bold cyan][E][/bold cyan] Email Intelligence     [dim]-[/dim] {email_count} services",
        "[bold cyan][R][/bold cyan] Risk Scoring",
        "[bold cyan][H][/bold cyan] Scan History & Diff",
        "[bold cyan][C][/bold cyan] Identity Correlation",
        "[bold cyan][A][/bold cyan] Remediation Actions",
        "[bold cyan][P][/bold cyan] Platform Health",
        "[bold cyan][S][/bold cyan] Cleanup / Secure Shred",
        "[bold cyan][G][/bold cyan] Optional GUI",
    ]
    return Text.from_markup("\n".join(lines))


def _home_examples_text() -> Text:
    example_lines = [f"[cyan]>[/cyan] {command}" for command in HOME_EXAMPLES]
    return Text.from_markup("\n".join(example_lines))


def _home_footer_text() -> Text:
    os_name = platform.system()
    return Text.from_markup(
        "\n".join(
            [
                "[dim]Cross-platform CLI-first privacy and OSINT toolkit[/dim]",
                "[dim]CLI home by default | GUI available with --gui[/dim]",
                f"[dim]Runtime: {os_name} | Rich terminal output[/dim]",
                "[bold green]trackher@osint ~ $[/bold green]",
            ]
        )
    )


def show_home_screen() -> None:
    """Render the terminal-native Trackher landing screen."""
    username_count, email_count = _home_catalog_counts()
    hero_body = Group(
        Align.left(_home_wordmark()),
        Rule(style="cyan"),
        Align.left(_home_features(username_count, email_count)),
        Rule(style="cyan"),
        Align.left(_home_footer_text()),
    )
    command_panel = Panel(
        Align.left(_home_examples_text()),
        border_style="cyan",
        box=box.SQUARE,
        title="[bold]Quick Commands[/bold]",
        padding=(1, 2),
    )

    shell = Panel(
        hero_body,
        border_style="cyan",
        box=box.SQUARE,
        title="[bold]TRACKHER[/bold]",
        padding=(1, 2),
    )
    console.print(Align.center(shell))
    console.print(Align.center(command_panel))
    console.print()


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


def print_risk_summary(risk: dict) -> None:
    """Render the explainable risk score summary."""
    score = int(risk.get("score", 0))
    level = str(risk.get("level", "LOW"))
    reasons = list(risk.get("reasons", []))
    disclaimer = str(risk.get("disclaimer", ""))

    level_styles = {
        "LOW": "green",
        "MEDIUM": "yellow",
        "HIGH": "bright_red",
        "CRITICAL": "bold red",
    }
    style = level_styles.get(level, "white")

    console.print(f"[bold cyan]Digital Footprint Risk Score[/bold cyan]")
    console.print(f"  [{style}]{score}/100 ({level})[/{style}]")
    if reasons:
        for reason in reasons:
            evidence = ", ".join(str(item) for item in reason.get("evidence", [])[:6])
            suffix = ""
            if len(reason.get("evidence", [])) > 6:
                suffix = ", ..."
            console.print(
                f"  [+{reason.get('points', 0)}] {reason.get('summary', 'Evidence')} "
                f"- {evidence}{suffix}"
            )
    else:
        console.print("  [dim]No verified or heuristic exposure evidence increased the score.[/dim]")
    if disclaimer:
        console.print(f"  [dim]{disclaimer}[/dim]\n")


def print_scan_diff(diff: dict) -> None:
    """Render a concise scan history diff summary."""
    if not diff.get("enabled", True):
        console.print("[dim]Local scan history is disabled for this run.[/dim]\n")
        return

    status = str(diff.get("status", "ok"))
    if not diff.get("available"):
        message = diff.get("message", "No previous matching scan in local history.")
        style = "yellow" if status == "corrupted" else "dim"
        console.print(f"[{style}]{message}[/{style}]\n")
        return

    previous_risk = diff.get("previous", {}).get("risk", {})
    current_risk = diff.get("current", {}).get("risk", {})
    previous_profile = str(diff.get("previous", {}).get("profile", "standard"))
    current_profile = str(diff.get("current", {}).get("profile", "standard"))
    risk_change = int(diff.get("risk_change", {}).get("value", 0))
    if risk_change > 0:
        change_label = f"↑ {risk_change}"
    elif risk_change < 0:
        change_label = f"↓ {abs(risk_change)}"
    else:
        change_label = "0"

    console.print("[bold cyan]SCAN DIFF[/bold cyan]")
    console.print(
        f"  Previous Risk: {previous_risk.get('score', 0)} {previous_risk.get('level', 'LOW')}"
    )
    console.print(
        f"  Current Risk:  {current_risk.get('score', 0)} {current_risk.get('level', 'LOW')}"
    )
    console.print(f"  Previous Profile: {previous_profile}")
    console.print(f"  Current Profile:  {current_profile}")
    console.print(f"  Change:        {change_label}")
    console.print(f"  New:           {len(diff.get('new_findings', []))}")
    console.print(f"  Resolved:      {len(diff.get('resolved_findings', []))}")
    console.print(f"  Unchanged:     {len(diff.get('unchanged_findings', []))}")

    if diff.get("profile_mismatch"):
        console.print(f"  [yellow]{diff.get('coverage_warning', '')}[/yellow]")

    new_breaches = diff.get("new_breaches", [])
    removed_breaches = diff.get("removed_breaches", [])
    if new_breaches or removed_breaches:
        console.print(f"  New Breaches:  {len(new_breaches)}")
        console.print(f"  Removed Breaches: {len(removed_breaches)}")

    def _sample(items: list[dict], heading: str) -> None:
        if not items:
            return
        labels = ", ".join(str(item.get("label", "")) for item in items[:5])
        suffix = ", ..." if len(items) > 5 else ""
        console.print(f"  {heading}: {labels}{suffix}")

    _sample(diff.get("new_findings", []), "New Findings")
    _sample(diff.get("resolved_findings", []), "Resolved Findings")
    _sample(new_breaches, "New Breaches")
    _sample(removed_breaches, "Removed Breaches")
    console.print()


def print_remediation_summary(remediation: dict, show_details: bool = False) -> None:
    """Render official remediation links without cluttering the main scan output."""
    if not remediation or not remediation.get("available"):
        return

    items = list(remediation.get("items", []))
    action_count = int(remediation.get("action_count", 0))

    console.print("[bold cyan]Remediation / Privacy Actions[/bold cyan]")
    console.print(
        f"  [bold white]{len(items)}[/bold white] findings include "
        f"[bold white]{action_count}[/bold white] official action links."
    )
    if not show_details:
        console.print("  [dim]Use --show-actions to display them.[/dim]\n")
        return

    for item in items:
        platform = str(item.get("platform", "Unknown"))
        status = str(item.get("status", "FOUND"))
        console.print(f"  [bold]{platform}[/bold] — {status}")
        for action in item.get("actions", []):
            label = str(action.get("label", "Action"))
            url = str(action.get("url", ""))
            console.print(f"    • {label}: [blue]{url}[/blue]")
        console.print()


def print_correlation_summary(correlation: dict, show_details: bool = False) -> None:
    """Render a compact summary of conservative identity correlations."""
    if not correlation or not correlation.get("available"):
        return

    items = list(correlation.get("items", []))
    style_map = {
        "HIGH": "bright_red",
        "MEDIUM": "yellow",
        "LOW": "green",
    }
    console.print("[bold cyan]Identity Correlation[/bold cyan]")
    console.print(
        f"  [bold white]{len(items)}[/bold white] likely cross-platform identity links."
    )

    for item in items[: (len(items) if show_details else 3)]:
        level = str(item.get("confidence", "LOW"))
        style = style_map.get(level, "white")
        console.print(
            f"  [{style}]{level}[/{style}] {item.get('summary', 'Unknown pair')} "
            f"({item.get('confidence_score', 0)}/100)"
        )
        evidence_labels = ", ".join(str(entry.get("label", "")) for entry in item.get("evidence", [])[:4])
        if evidence_labels:
            console.print(f"    {evidence_labels}")
        if show_details and item.get("penalties"):
            penalties = ", ".join(str(entry.get("label", "")) for entry in item.get("penalties", []))
            console.print(f"    penalties: {penalties}")

    disclaimer = str(correlation.get("disclaimer", ""))
    if disclaimer:
        console.print(f"  [dim]{disclaimer}[/dim]\n")
    else:
        console.print()


def print_platform_health_summary(health: dict, show_details: bool = False) -> None:
    """Render a concise platform/detector health summary."""
    if not health or not health.get("available"):
        return

    counts = dict(health.get("counts", {}))
    console.print("[bold cyan]Platform / Detector Health[/bold cyan]")
    console.print(
        f"  Healthy: {counts.get('HEALTHY', 0)} | "
        f"Degraded: {counts.get('DEGRADED', 0)} | "
        f"Broken: {counts.get('BROKEN', 0)} | "
        f"Unknown: {counts.get('UNKNOWN', 0)}"
    )

    if health.get("live_enabled"):
        console.print(
            f"  [dim]Live health enabled. Cache hits: {health.get('cache_hits', 0)}[/dim]"
        )
    else:
        console.print("  [dim]Offline schema health only.[/dim]")

    if not show_details:
        console.print()
        return

    for item in list(health.get("items", []))[:12]:
        console.print(
            f"  {item.get('state', 'UNKNOWN')}: "
            f"{item.get('scope', 'platform')} / {item.get('platform', 'Unknown')} "
            f"({item.get('detector', 'unknown')})"
        )
        console.print(f"    {item.get('detail', '')}")
    console.print()


def print_dry_run_table(items: list[dict]) -> None:
    """Render dry-run cleanup results as a table."""
    if not items:
        print_info("Temizlenecek dosya bulunamadi.")
        return

    table = Table(
        title="Kuru Calistirma (Dry-Run) Raporu",
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
        f"\n  [bold magenta]Toplam kazanilacak alan:[/bold magenta] "
        f"[bold white]{format_size(total_bytes)}[/bold white]\n"
    )


def username_unknown_cause_label(cause: object) -> str:
    key = str(cause or "unknown").strip() or "unknown"
    return USERNAME_UNKNOWN_CAUSE_LABELS.get(key, key.replace("_", " "))


def username_unknown_cause_counts(results: list[dict]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for result in results:
        if result.get("status") != "unknown":
            continue
        cause = str(result.get("unknown_cause", "unknown")).strip() or "unknown"
        counts[cause] += 1
    return counts


def format_username_unknown_breakdown(results: list[dict]) -> str:
    counts = username_unknown_cause_counts(results)
    if not counts:
        return ""

    parts: list[str] = []
    seen: set[str] = set()
    for cause in USERNAME_UNKNOWN_CAUSE_ORDER:
        if counts.get(cause):
            parts.append(f"{username_unknown_cause_label(cause)} {counts[cause]}")
            seen.add(cause)
    for cause in sorted(counts):
        if cause in seen:
            continue
        parts.append(f"{username_unknown_cause_label(cause)} {counts[cause]}")
    return ", ".join(parts)


def _email_accounts(results: dict | list) -> list[dict]:
    if isinstance(results, dict):
        return list(results.get("accounts", []))
    return list(results)


def _email_breaches(results: dict | list) -> list[dict]:
    if isinstance(results, dict):
        return list(results.get("breaches", []))
    return []


def print_email_results(
    email: str,
    results: dict | list[dict],
    show_manual: bool = False,
) -> None:
    """Render email OSINT results with clear passive/heuristic/manual grouping."""
    accounts = _email_accounts(results)
    breaches = _email_breaches(results)
    verified = [item for item in accounts if item.get("status") == "FOUND"]
    possible = [item for item in accounts if item.get("status") == "POSSIBLE"]
    not_found = [item for item in accounts if item.get("status") == "NOT_FOUND"]
    manual = [item for item in accounts if item.get("status") == "MANUAL"]
    unknown = [item for item in accounts if item.get("status") in {"UNKNOWN", "ERROR", "NOT_CONFIGURED"}]

    console.print(f"[bold cyan]E-posta OSINT - {email}[/bold cyan]\n")

    console.print("[bold green]Verified Accounts[/bold green]")
    if verified:
        for item in verified:
            detail = f" - {item.get('detail', '')}" if item.get("detail") else ""
            console.print(f"  [green]✓[/green] {item['service']}{detail}")
    else:
        console.print("  [dim]0 verified accounts discovered automatically.[/dim]")
        console.print("  [dim]This does not mean the email has no accounts on other services.[/dim]")

    console.print("\n[bold yellow]Possible Accounts[/bold yellow]")
    if possible:
        for item in possible:
            detail = f" - {item.get('detail', '')}" if item.get("detail") else ""
            console.print(f"  [yellow]~[/yellow] {item['service']}{detail}")
    else:
        console.print("  [dim]No possible heuristic matches.[/dim]")

    if not_found:
        console.print("\n[bold white]Checked and Not Found[/bold white]")
        for item in not_found:
            detail = f" - {item.get('detail', '')}" if item.get("detail") else ""
            console.print(f"  [dim]-[/dim] {item['service']}{detail}")

    if unknown:
        console.print("\n[bold yellow]Unknown / Errors[/bold yellow]")
        for item in unknown:
            detail = f" - {item.get('detail', '')}" if item.get("detail") else ""
            console.print(f"  [yellow]?[/yellow] {item['service']} ({item.get('status')}){detail}")

    console.print("\n[bold cyan]Manual Investigation[/bold cyan]")
    if manual:
        console.print(f"  [cyan]{len(manual)} services require manual review.[/cyan]")
        if show_manual:
            for item in manual:
                detail = f" - {item.get('detail', '')}" if item.get("detail") else ""
                console.print(f"  [cyan]>[/cyan] {item['service']}{detail}")
        else:
            console.print("  [dim]Use --show-manual to display them.[/dim]")
    else:
        console.print("  [dim]No manual services in catalog.[/dim]")

    console.print("\n[bold red]Breaches[/bold red]")
    if breaches:
        for item in breaches:
            if item.get("status") == "FOUND":
                console.print(f"  [red]![/red] {item['service']}: {len(item.get('breaches', []))} breaches")
            elif item.get("status") == "NOT_CONFIGURED":
                console.print(f"  [yellow]![/yellow] {item['service']}: NOT CONFIGURED")
            elif item.get("status") == "NOT_FOUND":
                console.print(f"  [dim]! {item['service']}: no known breaches[/dim]")
            else:
                console.print(f"  [yellow]![/yellow] {item['service']}: {item.get('status')}")
    else:
        console.print("  [dim]No breach providers configured in catalog.[/dim]")

    console.print()


def print_username_results(username: str, results: list[dict]) -> None:
    """Render username OSINT results as a table."""
    table = Table(
        title=f"Kullanici Adi Iz Surucu - {username}",
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
        result_status = result.get("status", "found" if result.get("found") else "not_found")
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
    breakdown = format_username_unknown_breakdown(results)
    console.print(
        f"\n  [bold magenta]Toplam:[/bold magenta] "
        f"[bold white]{found_count}[/bold white] platformda kayıt tespit edildi "
        f"([dim]{len(results)} servis tarandı, {unknown_count} sonuç doğrulanamadı[/dim]).\n"
    )
    if breakdown:
        console.print(f"  [dim]Doğrulanamayan nedenler: {breakdown}[/dim]\n")


def print_dork_results(target: str, dorks: list[dict]) -> None:
    """Render search engine dorks as a table."""
    table = Table(
        title=f"Arama Motoru Dork Sonuclari - {target}",
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
        "tarayiciya kopyalayarak derin arama yapabilirsiniz.\n"
    )
