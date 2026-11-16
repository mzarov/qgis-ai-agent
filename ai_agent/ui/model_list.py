from typing import Any

from qgis.PyQt.QtCore import QPoint
from qgis.PyQt.QtWidgets import QLineEdit, QMenu

from ai_agent.core.llm.probe_worker import ModelListThread
from ai_agent.i18n import tr
from ai_agent.ui import controls, icons, style
from ai_agent.ui import settings_fields as fields

MAX_ROWS = 12
MAX_SHOWN_CHARS = 64
ICON = 14
MODEL_KEY = "model_override"
SHOW_MODELS = tr("Show the server's models")
LOADING = tr("Loading the model list…")
NO_MODELS = tr("The server lists no models.")
MORE = tr("{0} more: type part of a name to narrow the list")
MODEL_HINT = tr("As the provider names it.")


def matching(names: list[str], typed: str) -> list[str]:
    wanted = typed.strip().casefold()
    # A name typed in full is the current choice, not a filter: the whole list is on offer.
    if not wanted or any(name.casefold() == wanted for name in names):
        return list(names)
    starts = [name for name in names if name.casefold().startswith(wanted)]
    holds = [name for name in names if wanted in name.casefold() and name not in starts]
    return starts + holds or list(names)


def shown(name: str) -> str:
    half = MAX_SHOWN_CHARS // 2
    short = name if len(name) <= MAX_SHOWN_CHARS else f"{name[:half]}…{name[-half:]}"
    # QMenu reads a lone ampersand as a mnemonic mark.
    return short.replace("&", "&&")


def listing_scope(overrides: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(value for key, value in overrides.items() if key != MODEL_KEY)


class ModelListMixin:
    _list_thread: ModelListThread | None
    _listed: dict[tuple[Any, ...], list[str]]
    _model_field: Any
    model_edit: Any

    def _offer_model_list(self, palette: Any) -> None:
        self._listed = {}
        glyph = icons.drawn("expanded", style.faint(palette), ICON)
        if glyph is None:
            return
        action = self.model_edit.addAction(glyph, QLineEdit.ActionPosition.TrailingPosition)
        action.setToolTip(SHOW_MODELS)
        action.triggered.connect(self._open_model_list)

    def _open_model_list(self, *_args: Any) -> None:
        if self._list_running() or not self._valid_url(self._edited_url()):
            return
        overrides = self._overrides()
        names = self._listed.get(listing_scope(overrides))
        if names is not None:
            self._show_models(names)
            return
        fields.set_row_hint(self._model_field, LOADING)
        thread = ModelListThread(overrides, self)
        thread.listed.connect(lambda names, problem: self._on_models_listed(overrides, names, problem))
        thread.finished.connect(lambda: self._on_list_finished(thread))
        self._list_thread = thread
        thread.start()

    def _on_models_listed(self, overrides: dict[str, Any], names: list[str], problem: str) -> None:
        if problem or not names:
            fields.set_row_hint(self._model_field, problem or NO_MODELS)
            return
        self._listed[listing_scope(overrides)] = names
        self._show_models(names)

    def _show_models(self, names: list[str]) -> None:
        fields.set_row_hint(self._model_field, MODEL_HINT)
        # The answer may arrive after the user left the page: a menu under a hidden field would hang in the air.
        if self.model_edit.isVisible():
            popup = self._models_menu(names)
            below = self.model_edit.mapToGlobal(QPoint(0, self.model_edit.height() + controls.MENU_GAP))
            popup.popup(below)

    def _models_menu(self, names: list[str]) -> QMenu:
        popup = controls.menu(self.model_edit, self.palette())
        popup.setMinimumWidth(self.model_edit.width())
        popup.aboutToHide.connect(popup.deleteLater)
        offered = matching(names, self.model_edit.text())
        for name in offered[:MAX_ROWS]:
            popup.addAction(shown(name)).triggered.connect(
                lambda _checked=False, chosen=name: self._choose_model(chosen)
            )
        if len(offered) > MAX_ROWS:
            popup.addSeparator()
            popup.addAction(MORE.format(len(offered) - MAX_ROWS)).setEnabled(False)
        return popup

    def _choose_model(self, name: str) -> None:
        if name != self.model_edit.text():
            self.model_edit.setText(name)
            self._model_chosen()

    def _on_list_finished(self, thread: ModelListThread) -> None:
        thread.deleteLater()
        if self._list_thread is thread:
            self._list_thread = None
            self._close_if_waiting()

    def _list_running(self) -> bool:
        return self._list_thread is not None and self._list_thread.isRunning()

    def _cancel_listing(self, *_args: Any) -> None:
        if self._list_running():
            self._list_thread.cancel()
        fields.set_row_hint(self._model_field, MODEL_HINT)
