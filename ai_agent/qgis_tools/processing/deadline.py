# No timer fires while an algorithm runs on the main thread: each feedback report checks the clock.

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
