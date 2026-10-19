from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk

from PIL import Image

from gui.tabs.cleanup import CleanupTabMixin
from gui.tabs.osint import OsintTabMixin
from gui.tabs.reports import ReportsMixin
from gui.tabs.research import ResearchTabMixin
from gui.tabs.intelligence import IntelligenceTabMixin
from gui.widgets.common import build_fonts, configure_theme, ctk
from gui.widgets.terminal import TERMINAL_COLORS, TerminalOutputMixin
from gui.widgets.results import ScanResultsMixin
from gui.workers import UiWorkerMixin
from utils.app_logging import configure_logging, get_logger, safe_log
from utils.app_paths import resource_path
from utils.profiles import DEFAULT_SCAN_PROFILE
from utils.runtime import validate_runtime
from utils import __version__


LOGGER = get_logger("gui")


class TrackherApp(
    ctk.CTk,
    UiWorkerMixin,
    TerminalOutputMixin,
    ScanResultsMixin,
    ReportsMixin,
    ResearchTabMixin,
    IntelligenceTabMixin,
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
        scaling = self._get_window_scaling()
        width = min(1180, int(self.winfo_screenwidth() / scaling) - 60)
        height = min(860, int(self.winfo_screenheight() / scaling) - 100)
        self.geometry(f'{width}x{height}+16+16')
        self.minsize(min(1040, width), min(740, height))

        self.bg_color = "#0b131e"
        self.fg_color = TERMINAL_COLORS['body']
        self.font_terminal, self.font_ui = build_fonts()
        self.configure(fg_color="#0c1420")

        self._setup_header()
        self._setup_tabs()
        self._setup_terminal()
        self._initialize_runtime_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_ui_drain()

    def _setup_header(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(padx=28, pady=(10, 4), fill="x")

        logo_path = resource_path("assets", "logo.jpg")
        if logo_path.exists():
            with Image.open(logo_path) as source_image:
                image = source_image.copy()
            self.logo_image = ctk.CTkImage(light_image=image, dark_image=image, size=(32, 32))
            self.lbl_logo = ctk.CTkLabel(self.header_frame, image=self.logo_image, text="")
            self.lbl_logo.pack(side="left", padx=(0, 12))

        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="TRACKHER",
            font=ctk.CTkFont(size=25, weight="bold"),
            text_color="#50d7e8",
        )
        self.lbl_title.pack(side="left")
        ctk.CTkLabel(self.header_frame, text="DİJİTAL AYAK İZİ & GİZLİLİK", text_color="#91a4ba", font=ctk.CTkFont(size=11)).pack(side="left", padx=20)
        ctk.CTkLabel(self.header_frame, text=f"  LOCAL WORKSPACE  /  v{__version__}  ", corner_radius=8, fg_color="#182638", text_color="#a8bfd5", font=ctk.CTkFont(size=11), height=30).pack(side="right")
        status = ctk.CTkFrame(self, fg_color='transparent')
        status.pack(fill='x', padx=28, pady=(0, 4))
        self.scan_status = ctk.CTkLabel(status, text='Hazır · Bir arama başlatın', height=20, text_color='#91a4ba', anchor='w', font=ctk.CTkFont(size=12))
        self.scan_status.pack(side='left')
        self.scan_progress = ctk.CTkProgressBar(status, width=190, height=4, fg_color='#223346', progress_color='#50d7e8')
        self.scan_progress.set(0)
        self.scan_progress.pack(side='right', padx=4)
        self.stop_scan_button = ctk.CTkButton(status, text='Durdur', width=70, height=24, state='disabled', command=self._stop_scan, fg_color='#71394c')
        self.stop_scan_button.pack(side='right', padx=4)
        self.pause_scan_button = ctk.CTkButton(status, text='Beklet', width=70, height=24, state='disabled', command=self._toggle_scan_pause, fg_color='#233b52')
        self.pause_scan_button.pack(side='right', padx=4)
        ctk.CTkButton(status, text='Araştırma', width=85, height=24, command=lambda: self.tabview.set('Araştırma'), fg_color='#233b52').pack(side='right', padx=4)

    def _setup_tabs(self):
        self.tabview = ctk.CTkTabview(
            self,
            width=860,
            height=600,
            fg_color="#0c1420",
            segmented_button_fg_color="#192737",
            segmented_button_selected_color="#164c5d",
            segmented_button_selected_hover_color="#206579",
            segmented_button_unselected_color="#192737",
            segmented_button_unselected_hover_color="#263b51",
        )
        self.tabview.pack(padx=24, pady=(0, 8), fill="both", expand=True)
        self.tabview.add("OSINT")
        self.tabview.add("Cleaner")
        self.tabview.add("Shredder")
        self.tabview.add("Araştırma")
        self.setup_osint_tab()
        self.setup_cleaning_tab()
        self.setup_shredder_tab()
        self.setup_research_tab()

    def _setup_terminal(self):
        self.log_frame = ctk.CTkFrame(self, fg_color='transparent')
        self.log_frame.pack(side='bottom', fill='x', padx=28, pady=(0, 16))
        self.lbl_term = ctk.CTkLabel(self.log_frame, text="İŞLEM GÜNLÜĞÜ", text_color='#91a4ba', font=ctk.CTkFont(size=11, weight='bold'))
        self.lbl_term.pack(anchor="w", pady=(0, 3))
        self.terminal = ctk.CTkTextbox(
            self.log_frame,
            width=860,
            height=44,
            fg_color=self.bg_color,
            text_color=self.fg_color,
            font=self.font_terminal,
            wrap="word",
            border_width=1,
            border_color="#26384b",
            state="disabled",
        )
        self.terminal.pack(fill="x")
        for category, color in TERMINAL_COLORS.items():
            self.terminal.tag_config(category, foreground=color)
        # Reserve the log's height before assigning the remaining space to tabs.
        self.tabview.pack_forget()
        self.tabview.pack(padx=24, pady=(0, 8), fill='both', expand=True)

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
