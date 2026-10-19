from collections.abc import Callable
from typing import Any

from qgis.core import QgsApplication, QgsFeedback, QgsMessageLog, QgsTask
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

LOG_TAG = "AI Agent"
STOPPED = "Stopped before it finished; nothing of this step was kept."
MS_IN_SECOND = 1000
# QGIS holds only references to a task's context and feedback: keep each work alive until it ends.
_RUNNING: set["Background"] = set()


class Background(QObject):
    progressed = pyqtSignal(float)
    counted = pyqtSignal(int)
    finished = pyqtSignal(object)

    def __init__(self, seconds: float | None = None, timeout_message: str = "") -> None:
        super().__init__()
        self.seconds = seconds
        self._timeout_message = timeout_message
        self._stopped_because: BaseException | None = None
        self._launch_error: BaseException | None = None
        self._over = False
        self._limit = QTimer(self)
        self._limit.setSingleShot(True)
        self._limit.timeout.connect(self._time_out)

    def start(self) -> None:
        # `finished` never arrives before this returns, even when the launch fails.
        _RUNNING.add(self)
        if self.seconds is not None:
            self._limit.start(int(self.seconds * MS_IN_SECOND))
        try:
            self._launch()
        except Exception as err:
            self._launch_error = err
            QTimer.singleShot(0, self._launch_failed)

    def cancel(self) -> None:
        self._stop(RuntimeError(STOPPED))

    def _launch(self) -> None:
        raise NotImplementedError

    def _launch_failed(self) -> None:
        self._end(self._launch_error)

    def _halt(self) -> None:
        raise NotImplementedError

    def _time_out(self) -> None:
        self._stop(TimeoutError(self._timeout_message.format(seconds=int(self.seconds or 0))))

    def _stop(self, reason: BaseException) -> None:
        if self._over or self._stopped_because is not None:
            return
        self._stopped_because = reason
        self._halt()

    def _report(self, percent: float) -> None:
        if not self._over:
            self.progressed.emit(float(percent))

    def _count(self, done: int) -> None:
        if not self._over:
            self.counted.emit(int(done))

    def _end(self, outcome: object) -> None:
        if self._over:
            return
        self._over = True
        self._limit.stop()
        _RUNNING.discard(self)
        self.finished.emit(self._stopped_because or outcome)


class InTask(Background):
    # `work` runs in a QGIS task: it may touch only its arguments and thread-safe QGIS classes.
    def __init__(
        self,
        description: str,
        work: Callable[[QgsFeedback], Any],
        complete: Callable[[Any], dict[str, Any]],
    ) -> None:
        super().__init__()
        self._description = description
        self._work = work
        self._complete = complete
        self._task: _Worker | None = None

    def _launch(self) -> None:
        self._task = _Worker(self._description, self._work, self._finished)
        self._task.progressChanged.connect(self._report)
        self._task.feedback.processedCountChanged.connect(self._count)
        QgsApplication.taskManager().addTask(self._task)

    def _halt(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def _finished(self, value: Any, error: BaseException | None) -> None:
        # The task manager deletes the task after this: nothing may reach it from now on.
        self._task = None
        if error is not None or self._stopped_because is not None:
            # A stop that came while this call waited in the queue still keeps nothing.
            self._end(error)
            return
        try:
            self._end(self._complete(value))
        except Exception as err:
            self._end(err)


def download_progress(feedback: Any) -> Callable[[int, int], None]:
    def report(received: int, total: int) -> None:
        feedback.setProcessedCount(max(0, int(received)))
        if total > 0:
            feedback.setProgress(min(100.0, 100.0 * received / total))

    return report


class _Worker(QgsTask):
    def __init__(
        self,
        description: str,
        work: Callable[[QgsFeedback], Any],
        done: Callable[[Any, BaseException | None], None],
    ) -> None:
        super().__init__(description, QgsTask.Flag.CanCancel | QgsTask.Flag.Hidden)
        self._work = work
        self._done = done
        self.feedback = QgsFeedback()
        self.feedback.progressChanged.connect(self.setProgress)
        self._value: Any = None
        self._error: BaseException | None = None

    def run(self) -> bool:
        try:
            self._value = self._work(self.feedback)
        except BaseException as err:
            # Never out of run(): an exception crossing back into C++ would take QGIS down.
            self._error = err
            return False
        return not self.feedback.isCanceled()

    def cancel(self) -> None:
        self.feedback.cancel()
        super().cancel()

    def finished(self, result: bool) -> None:
        error = self._error
        if not result and error is None:
            error = RuntimeError(STOPPED)
        try:
            self._done(self._value, error)
        except Exception as err:
            QgsMessageLog.logMessage(f"A background step failed to finish ({type(err).__name__}).", LOG_TAG)
