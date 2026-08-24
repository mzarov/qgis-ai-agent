from typing import Any

from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.agent.loop import AgentLoop
from qgis_ai_agent.core.orchestrator.contracts import DockWidgetContract
from qgis_ai_agent.core.state.history import HistoryStore
from qgis_ai_agent.qgis_tools.registry import summarize_tool_call

LOG_TAG = "QGIS AI Agent"


class CoreOrchestrator:
    """
    Связывает события UI с агентным циклом и рендерит его ход в чат.
    Всю логику принятия решений держит цикл, здесь остаётся только отображение.
    """

    def __init__(self, iface: Any, dock_widget: DockWidgetContract):
        self.iface = iface
        self.dock_widget = dock_widget
        self.history_store = HistoryStore(max_messages=14)
        self.agent = AgentLoop()
        self._active_tool_message_id: int | None = None
        self._plan_message_id: int | None = None
        self._connect_agent()

    def _connect_agent(self) -> None:
        """Подписывается на сигналы агентного цикла."""
        self.agent.tool_started.connect(self.on_tool_started)
        self.agent.tool_finished.connect(self.on_tool_finished)
        self.agent.tool_queued.connect(self.on_tool_queued)
        self.agent.skill_loaded.connect(self.on_skill_loaded)
        self.agent.confirm_needed.connect(self.on_confirm_needed)
        self.agent.applied.connect(self.on_applied)
        self.agent.finished.connect(self.on_finished)
        self.agent.failed.connect(self.on_failed)
        self.agent.busy_changed.connect(self.dock_widget.set_busy)

    def on_prompt(self, prompt: str) -> None:
        """Пользователь отправил запрос — запускаем новый прогон агента."""
        text = (prompt or "").strip()
        if not text:
            self._push_message("Введите запрос.", Qgis.Warning)
            return
        if self.agent.is_running:
            self.dock_widget.add_system_message("Дождитесь окончания текущей задачи.")
            return

        self.dock_widget.add_user_message(text)
        self.dock_widget.prompt_edit.clear()
        self.dock_widget.set_confirm_visible(False)
        self._plan_message_id = None
        history = self.history_store.get()
        self.history_store.add("user", text)
        self.agent.start(text, history)

    def on_tool_started(self, summary: str) -> None:
        """Тул начал выполняться — показываем строку активности."""
        self._active_tool_message_id = self.dock_widget.add_tool_message(summary)

    def on_tool_finished(self, tool_name: str, ok: bool) -> None:
        """Тул отработал — помечаем строку активности."""
        if self._active_tool_message_id is not None:
            self.dock_widget.mark_tool_done(self._active_tool_message_id, ok)
            self._active_tool_message_id = None
        if not ok:
            QgsMessageLog.logMessage(f"Тул {tool_name} завершился ошибкой.", LOG_TAG, Qgis.Warning)

    def on_tool_queued(self, summary: str) -> None:
        """Изменение попало в очередь на подтверждение."""
        QgsMessageLog.logMessage(f"В план добавлено: {summary}", LOG_TAG, Qgis.Info)

    def on_skill_loaded(self, name: str) -> None:
        """Агент подгрузил домен знаний."""
        self.dock_widget.add_tool_message(f"Загружаю знания: {name}")

    def on_confirm_needed(self, calls: list, final_text: str) -> None:
        """Агент закончил и предлагает применить накопленные изменения."""
        if final_text:
            self.dock_widget.add_result_message(final_text)
            self.history_store.add("assistant", final_text)
        lines = [
            f"{index}. {summarize_tool_call(call.name, call.arguments)}"
            for index, call in enumerate(calls, 1)
        ]
        self._plan_message_id = self.dock_widget.add_plan_message(lines)
        self.dock_widget.set_confirm_visible(True)
        self.dock_widget.add_system_message(
            f"Изменений к применению: {len(calls)}. Нажмите «Применить изменения» или «Отмена»."
        )

    def on_confirm_plan(self) -> None:
        """Пользователь подтвердил батч изменений."""
        if not self.agent.has_pending_writes:
            self.dock_widget.add_system_message("Нет изменений для применения.")
            return
        self.dock_widget.set_confirm_visible(False)
        self.agent.confirm_pending()

    def on_cancel_plan(self) -> None:
        """Пользователь отменил батч изменений."""
        self.agent.cancel_pending()
        self.dock_widget.set_confirm_visible(False)
        self._plan_message_id = None
        self.dock_widget.add_system_message("Изменения отменены, проект не тронут.")

    def on_applied(self, results: list) -> None:
        """Батч применён — показываем итог."""
        failed = [result for result in results if not result.ok]
        if self._plan_message_id is not None and not failed:
            self.dock_widget.mark_plan_completed(self._plan_message_id)
        self._plan_message_id = None
        if failed:
            details = "; ".join(str(result.payload.get("error", "")) for result in failed)
            self.dock_widget.add_system_message(f"Часть шагов не выполнена: {details}")
            self._push_message("Не все изменения применены.", Qgis.Warning)
            return
        self.dock_widget.add_result_message(
            f"Готово: применено шагов — {len(results)}.{self._where_to_look(results)}"
        )
        self._push_message("Изменения применены.", Qgis.Success)

    @staticmethod
    def _where_to_look(results: list) -> str:
        """Подсказка, где смотреть результат — зависит от того, что реально делалось."""
        hints = []
        if any("layout_name" in result.payload for result in results):
            hints.append("макет — в Проект → Менеджер макетов")
        if any("outputs" in result.payload for result in results):
            hints.append("новые слои — на панели слоёв")
        return " Смотрите: " + ", ".join(hints) + "." if hints else ""

    def _push_message(self, text: str, level) -> None:
        """Сообщение в шину QGIS с автоскрытием, чтобы старые плашки не висели."""
        self.iface.messageBar().pushMessage("QGIS AI Agent", text, level=level, duration=8)

    def on_finished(self, text: str) -> None:
        """Агент закончил без изменений проекта — это ответ на вопрос."""
        message = (text or "").strip()
        if not message:
            self.dock_widget.add_system_message("Модель не вернула ответ. Попробуйте переформулировать.")
            return
        self.dock_widget.add_result_message(message)
        self.history_store.add("assistant", message)

    def on_failed(self, message: str) -> None:
        """Прогон упал — показываем ошибку и снимаем состояние ожидания."""
        self.dock_widget.set_confirm_visible(False)
        self._active_tool_message_id = None
        self._plan_message_id = None
        self.dock_widget.add_system_message(f"Ошибка: {message}")
        self._push_message(message, Qgis.Critical)

    def shutdown(self) -> None:
        """Останавливает активный запрос при выгрузке плагина."""
        self.agent.stop()
