from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk

from PIL import Image

from gui.tabs.cleanup import CleanupTabMixin
from gui.tabs.osint import OsintTabMixin
from gui.tabs.reports import ReportsMixin
from gui.widgets.common import build_fonts, configure_theme, ctk
from gui.widgets.terminal import TerminalOutputMixin
from gui.workers import UiWorkerMixin
from utils.app_logging import configure_logging, get_logger, safe_log
from utils.app_paths import resource_path
from utils.profiles import DEFAULT_SCAN_PROFILE
from utils.runtime import validate_runtime


LOGGER = get_logger("gui")


class TrackherApp(
    ctk.CTk,
    UiWorkerMixin,
    TerminalOutputMixin,
    ReportsMixin,
    OsintTabMixin,
    CleanupTabMixin,
):
    """Trackher's existing root window and shared GUI state."""

    def __init__(self):
        configure_theme()
        configure_logging()
        super().__init__()
        self._ui_queue = queue.Queue()
        self._ui_state_lock = threading.Lock()
        self._closing = threading.Event()
        self._queue_after_id = None
        self._terminal_line_count = 0
        self.profile_var = tk.StringVar(value=DEFAULT_SCAN_PROFILE)
        self.health_live_var = tk.IntVar(value=0)

        self.title("Trackher - Digital Footprint & Privacy Toolkit")
        self.geometry("900x700")
        self.minsize(800, 650)

        self.bg_color = "#0c0c0c"
        self.fg_color = "#00ff00"
        self.font_terminal, self.font_ui = build_fonts()
        self.configure(fg_color="#181818")

        self._setup_header()
        self._setup_tabs()
        self._setup_terminal()
        self._initialize_runtime_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_ui_drain()

    def _setup_header(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=(15, 5))

        logo_path = resource_path("assets", "logo.jpg")
        if logo_path.exists():
            with Image.open(logo_path) as source_image:
                image = source_image.copy()
            self.logo_image = ctk.CTkImage(light_image=image, dark_image=image, size=(40, 40))
            self.lbl_logo = ctk.CTkLabel(self.header_frame, image=self.logo_image, text="")
            self.lbl_logo.pack(side="left", padx=(0, 10))

        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="TRACKHER",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#00d2ff",
        )
        self.lbl_title.pack(side="left")

    def _setup_tabs(self):
        self.tabview = ctk.CTkTabview(
            self,
            width=860,
            height=200,
            fg_color="#242424",
            segmented_button_fg_color="#333333",
        )
        self.tabview.pack(padx=20, pady=5, fill="x")
        self.tabview.add("OSINT")
        self.tabview.add("Cleaner")
        self.tabview.add("Shredder")
        self.setup_osint_tab()
        self.setup_cleaning_tab()
        self.setup_shredder_tab()

    def _setup_terminal(self):
        self.lbl_term = ctk.CTkLabel(self, text="Terminal Output:", font=self.font_ui)
        self.lbl_term.pack(anchor="w", padx=20, pady=(10, 0))
        self.terminal = ctk.CTkTextbox(
            self,
            width=860,
            height=300,
            fg_color=self.bg_color,
            text_color=self.fg_color,
            font=self.font_terminal,
            wrap="word",
            border_width=2,
            border_color="#333",
            state="disabled",
        )
        self.terminal.pack(padx=20, pady=(0, 20), fill="both", expand=True)

    def _initialize_runtime_status(self):
        self.print_to_terminal("root@trackher:~# System initialized.")
        self.print_to_terminal("root@trackher:~# Modules loaded. Awaiting instructions...\n")
        runtime_state = validate_runtime()
        for warning in runtime_state.get("warnings", []):
            self.print_to_terminal(f"  [i] Runtime warning: {warning}")
        if runtime_state.get("warnings"):
            safe_log(
                LOGGER,
                logging.WARNING,
                "GUI runtime validation warnings: %s",
                runtime_state.get("warnings"),
            )
        self._refresh_cached_health_summary()


def launch() -> None:
    """Run the GUI directly while keeping main.py's explicit GUI path unchanged."""
    app = TrackherApp()
    app.mainloop()
