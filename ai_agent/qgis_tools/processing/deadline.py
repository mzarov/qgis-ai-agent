"""A Processing feedback that cancels its algorithm once it has run past the tool timeout.

Algorithms run on the main thread, so no timer can fire while one works. They do
report as they go — progress, info lines — and check for cancellation between
chunks of work, so every report is a moment to look at the clock and cancel.
An algorithm that never reports cannot be stopped this way; the limit still
names itself in the error once it returns.
"""

import time
from collections.abc import Callable
from typing import Any

from qgis.core import QgsProcessingFeedback

TIMED_OUT = (
    "The algorithm ran past the {seconds} s tool timeout and was stopped. Try a smaller extent or fewer "
    "features; the user can raise the limit in Settings → Advanced."
)


class DeadlineFeedback(QgsProcessingFeedback):
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic):
        super().__init__()
        self.seconds = seconds
        self.timed_out = False
        self._clock = clock
        self._deadline = clock() + seconds
        self.progressChanged.connect(self._check)

    def setProgressText(self, text: str) -> None:
        self._check()
        super().setProgressText(text)

    def pushInfo(self, info: str) -> None:
        self._check()
        super().pushInfo(info)

    def pushDebugInfo(self, info: str) -> None:
        self._check()
        super().pushDebugInfo(info)

    def pushCommandInfo(self, info: str) -> None:
        self._check()
        super().pushCommandInfo(info)

    def pushConsoleInfo(self, info: str) -> None:
        self._check()
        super().pushConsoleInfo(info)

    def timeout_message(self) -> str:
        return TIMED_OUT.format(seconds=int(self.seconds))

    def _check(self, *_args: Any) -> None:
        if not self.timed_out and self._clock() >= self._deadline:
            self.timed_out = True
            self.cancel()
