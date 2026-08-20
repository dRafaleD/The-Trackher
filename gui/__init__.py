"""Public compatibility exports for the Trackher GUI."""

from gui.app import LOGGER, TrackherApp, launch
from gui.widgets.terminal import TERMINAL_MAX_LINES, TERMINAL_RETAIN_LINES

__all__ = [
    "LOGGER",
    "TERMINAL_MAX_LINES",
    "TERMINAL_RETAIN_LINES",
    "TrackherApp",
    "launch",
]
