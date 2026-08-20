from __future__ import annotations

import platform

try:
    import customtkinter as ctk
except ImportError as exc:
    raise ImportError(
        "customtkinter eksik; 'pip install -r requirements.txt' calistirin"
    ) from exc


def configure_theme() -> None:
    """Apply the existing application-wide CustomTkinter theme."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")


def build_fonts() -> tuple[ctk.CTkFont, ctk.CTkFont]:
    """Return the existing platform-appropriate terminal and UI fonts."""
    font_map = {
        "Windows": ("Consolas", "Segoe UI"),
        "Darwin": ("Menlo", "Helvetica Neue"),
        "Linux": ("DejaVu Sans Mono", "DejaVu Sans"),
    }
    terminal_font, ui_font = font_map.get(platform.system(), ("Courier", "Helvetica"))
    return (
        ctk.CTkFont(family=terminal_font, size=13),
        ctk.CTkFont(family=ui_font, size=13, weight="bold"),
    )


def format_result_sample(items: list[dict], key: str, limit: int = 5) -> str:
    """Build a short, deduplicated sample string from result rows."""
    labels: list[str] = []
    for item in items:
        value = str(item.get(key, "")).strip()
        if not value or value in labels:
            continue
        labels.append(value)
        if len(labels) >= limit:
            break

    if not labels:
        return ""
    suffix = " ..." if len(items) > len(labels) else ""
    return ", ".join(labels) + suffix
