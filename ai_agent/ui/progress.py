"""The status line at the foot of the conversation: the searching compass, "Working…", the time.

The compass here is the panel's one live mark; its needle swings while the agent works.

The current call is named in the open activity list above it, so the line does not repeat it.

It lives in the feed under the last message, so it scrolls with the
conversation instead of sitting on the composer.
"""

import time
from typing import Any

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QHBoxLayout, QWidget

from ai_agent.i18n import tr
from ai_agent.ui import compass, controls, style
from ai_agent.ui.durations import format_seconds

# The elapsed time shows whole seconds; a quarter-second tick keeps it on time without busy repaints.
TICK_MS = 250
MARK = 18
WORKING = tr("Working…")


class ProgressLine(QWidget):
    def __init__(self, palette: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._started = 0.0
        line = QHBoxLayout(self)
        line.setContentsMargins(2, 4, 2, 4)
        line.setSpacing(10)
        self.compass = compass.Compass(MARK, palette)
        line.addWidget(self.compass, 0, Qt.AlignmentFlag.AlignVCenter)
        self._step = controls.ElidedLabel(WORKING)
        self._step.setStyleSheet(f"color: {style.css_color(style.text(palette))};")
        line.addWidget(self._step, 1)
        self._elapsed = controls.small("", palette)
        self._elapsed.setWordWrap(False)
        line.addWidget(self._elapsed)
        self._shown_second = -1
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self.hide()

    @property
    def step_text(self) -> str:
        return self._step.text()

    def start(self) -> None:
        self._started = time.monotonic()
        self._step.setText(WORKING)
        self._step.setToolTip(WORKING)
        self._shown_second = 0
        self._elapsed.setText(format_seconds(0, decimals=0))
        self.compass.set_state(compass.SEARCH)
        self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.compass.stop()
        self.hide()

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._started
        # The text changes once a second; setting it every frame would relayout for nothing.
        if int(elapsed) != self._shown_second:
            self._shown_second = int(elapsed)
            self._elapsed.setText(format_seconds(elapsed, decimals=0))
