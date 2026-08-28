import builtins
import io
import sys
import traceback
from contextlib import redirect_stdout
from typing import Any

MAX_LINES = 200000
MAX_OUTPUT_CHARS = 4000
TRUNCATION_NOTE = "… (output truncated)"
BUDGET_MESSAGE = (
    "The snippet ran past {limit} executed lines and was stopped. It is most "
    "likely an endless loop — rewrite it without one."
)


class BudgetExceeded(RuntimeError):
    pass


class LineBudget:
    def __init__(self, limit: int = MAX_LINES):
        self.limit = limit
        self.used = 0
        self._previous: Any = None

    def __enter__(self) -> "LineBudget":
        self._previous = sys.gettrace()
        sys.settrace(self._trace)
        return self

    def __exit__(self, *exc_info: Any) -> None:
        sys.settrace(self._previous)

    def _trace(self, frame: Any, event: str, arg: Any) -> Any:
        if event == "line":
            self.used += 1
            if self.used > self.limit:
                raise BudgetExceeded(BUDGET_MESSAGE.format(limit=self.limit))
        return self._trace


def build_globals() -> dict[str, Any]:
    import qgis.core as core
    import qgis.PyQt.QtCore as qtcore
    import qgis.PyQt.QtGui as qtgui

    prepared: dict[str, Any] = {"__builtins__": builtins}
    for module in (core, qtcore, qtgui):
        for name in dir(module):
            if name.startswith("Qgs") or name.startswith("Q"):
                prepared[name] = getattr(module, name)
    prepared["qgis"] = sys.modules.get("qgis")
    prepared["QgsProject"] = core.QgsProject
    prepared["project"] = core.QgsProject.instance()
    prepared["iface"] = _iface()
    try:
        import processing

        prepared["processing"] = processing
    except Exception:
        pass
    return prepared


def run_snippet(code: str, limit: int = MAX_LINES) -> dict[str, Any]:
    prepared = build_globals()
    stream = io.StringIO()
    budget = LineBudget(limit)
    try:
        with redirect_stdout(stream), budget:
            exec(compile(code, "<agent snippet>", "exec"), prepared)  # noqa: S102
    except BudgetExceeded as stopped:
        return _result(stream, budget, error=str(stopped), traceback_text="")
    except BaseException as failure:
        return _result(stream, budget, error=str(failure), traceback_text=_short_traceback())
    return _result(stream, budget)


def _result(stream: io.StringIO, budget: LineBudget, error: str = "", traceback_text: str = "") -> dict[str, Any]:
    output = stream.getvalue()
    result: dict[str, Any] = {"output": _clipped(output), "lines_executed": budget.used}
    if not output.strip():
        result["output_note"] = "The snippet printed nothing — use print() to report what you found."
    if error:
        result["error"] = error
        if traceback_text:
            result["traceback"] = traceback_text
    return result


def _clipped(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + TRUNCATION_NOTE


def _short_traceback() -> str:
    return _clipped("".join(traceback.format_exception(*sys.exc_info())[1:]))


def _iface() -> Any:
    try:
        from qgis.utils import iface

        return iface
    except Exception:
        return None
