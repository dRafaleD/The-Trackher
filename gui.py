"""Compatibility launcher for direct ``python gui.py`` usage.

The GUI implementation lives in the :mod:`gui` package. Normal imports resolve
to that package and keep ``from gui import TrackherApp`` compatible.
"""

from gui.app import TrackherApp, launch
from gui.widgets.terminal import TERMINAL_MAX_LINES, TERMINAL_RETAIN_LINES

__all__ = [
    "TERMINAL_MAX_LINES",
    "TERMINAL_RETAIN_LINES",
    "TrackherApp",
    "launch",
]


if __name__ == "__main__":
    launch()
