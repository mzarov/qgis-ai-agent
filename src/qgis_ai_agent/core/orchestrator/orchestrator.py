from typing import Any

from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.agent.loop import AgentLoop
from qgis_ai_agent.core.orchestrator.contracts import DockWidgetContract
from qgis_ai_agent.core.state.conversation import ConversationState
from qgis_ai_agent.qgis_tools.registry import summarize_tool_call

LOG_TAG = "QGIS AI Agent"
MESSAGE_DURATION_SEC = 8
SESSION_MISSING = "Диалог не найден."
SWITCH_WHILE_RUNNING = "Дождитесь окончания текущей задачи."
SWITCH_WHILE_PENDING = "Сначала примените или отмените запланированные изменения."


class CoreOrchestrator:
    def __init__(self, iface: Any, dock_widget: DockWidgetContract):
        self.iface = iface
        self.dock_widget = dock_widget
        self.conversation = ConversationState()
        self.agent = AgentLoop()
        self._active_tool_message_id: int | None = None
        self._plan_message_id: int | None = None
        self._connect_agent()
        self.dock_widget.set_session_source(self.conversation.recent)

    def _connect_agent(self) -> None:
        self.agent.tool_started.connect(self.on_tool_started)
        self.agent.tool_finished.connect(self.on_tool_finished)
        self.agent.tool_queued.connect(self.on_tool_queued)
        self.agent.tool_rejected.connect(self.on_tool_rejected)
        self.agent.skill_loaded.connect(self.on_skill_loaded)
        self.agent.confirm_needed.connect(self.on_confirm_needed)
        self.agent.applied.connect(self.on_applied)
        self.agent.finished.connect(self.on_finished)
        self.agent.failed.connect(self.on_failed)
        self.agent.busy_changed.connect(self.dock_widget.set_busy)

    def on_new_session(self) -> None:
        if self._busy_with_current():
            return
        self.conversation.start_new()
        self._replay()

    def on_session_chosen(self, identifier: str) -> None:
        if self._busy_with_current():
            return
        if not self.conversation.restore(identifier):
            self.dock_widget.add_system_message(SESSION_MISSING)
            return
        self._replay()

    def _busy_with_current(self) -> bool:
        if self.agent.is_running:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return True
        if self.agent.has_pending_writes:
            self.dock_widget.add_system_message(SWITCH_WHILE_PENDING)
            return True
        return False

    def _replay(self) -> None:
        self._plan_message_id = None
        self._active_tool_message_id = None
        self.dock_widget.replay(self.conversation.messages)

    def on_prompt(self, prompt: str) -> None:
        text = (prompt or "").strip()
        if not text:
            self._push_message("Введите запрос.", Qgis.Warning)
            return
        if self.agent.is_running:
            self.dock_widget.add_system_message("Дождитесь окончания текущей задачи.")
            return

        self.dock_widget.add_user_message(text)
        self.dock_widget.clear_prompt()
        self._plan_message_id = None
        history = self.conversation.window()
        self.conversation.add("user", text)
        self.agent.start(text, history)

    def on_tool_started(self, summary: str) -> None:
        self._active_tool_message_id = self.dock_widget.add_tool_message(summary)

    def on_tool_finished(self, tool_name: str, ok: bool) -> None:
        if self._active_tool_message_id is not None:
            self.dock_widget.mark_tool_done(self._active_tool_message_id, ok)
            self._active_tool_message_id = None
        if not ok:
            QgsMessageLog.logMessage(f"Тул {tool_name} завершился ошибкой.", LOG_TAG, Qgis.Warning)

    def on_tool_queued(self, summary: str) -> None:
        QgsMessageLog.logMessage(f"В план добавлено: {summary}", LOG_TAG, Qgis.Info)

    def on_tool_rejected(self, summary: str) -> None:
        self.dock_widget.add_rejected_message(f"Отклонено: {summary}")

    def on_skill_loaded(self, name: str) -> None:
        self.dock_widget.add_tool_message(f"Загружаю знания: {name}")

    def on_confirm_needed(self, calls: list, final_text: str) -> None:
        if final_text:
            self.dock_widget.add_result_message(final_text)
            self.conversation.add("assistant", final_text)
        lines = [
            f"{index}. {summarize_tool_call(call.name, call.arguments)}"
            for index, call in enumerate(calls, 1)
        ]
        self._plan_message_id = self.dock_widget.add_plan_message(lines)

    def on_confirm_plan(self) -> None:
        if not self.agent.has_pending_writes:
            self.dock_widget.add_system_message("Нет изменений для применения.")
            return
        self.agent.confirm_pending()

    def on_cancel_plan(self) -> None:
        self.agent.cancel_pending()
        if self._plan_message_id is not None:
            self.dock_widget.mark_plan_cancelled(self._plan_message_id)
        self._plan_message_id = None

    def on_applied(self, results: list) -> None:
        failed = [result for result in results if not result.ok]
        if self._plan_message_id is not None and not failed:
            self.dock_widget.mark_plan_completed(self._plan_message_id)
        self._plan_message_id = None
        if failed:
            details = "; ".join(str(result.payload.get("error", "")) for result in failed)
            outcome = f"Часть шагов не выполнена: {details}"
            self.dock_widget.add_system_message(outcome)
            self.conversation.add("assistant", outcome)
            self._push_message("Не все изменения применены.", Qgis.Warning)
            return
        outcome = f"Готово: применено шагов — {len(results)}.{self._where_to_look(results)}"
        self.dock_widget.add_result_message(outcome)
        self.conversation.add("assistant", outcome)
        self._push_message("Изменения применены.", Qgis.Success)

    def on_finished(self, text: str) -> None:
        message = (text or "").strip()
        if not message:
            self.dock_widget.add_system_message(
                "Модель не вернула ответ. Попробуйте переформулировать."
            )
            return
        self.dock_widget.add_result_message(message)
        self.conversation.add("assistant", message)

    def on_failed(self, message: str) -> None:
        self._active_tool_message_id = None
        self._plan_message_id = None
        self.dock_widget.add_system_message(f"Ошибка: {message}")
        self._push_message(message, Qgis.Critical)

    def shutdown(self) -> None:
        self.conversation.save()
        self.agent.stop()

    @staticmethod
    def _where_to_look(results: list) -> str:
        names = [
            result.payload.get("result_layer_name")
            for result in results
            if result.payload.get("result_layer_name")
        ]
        if names:
            return " Новые слои: " + ", ".join(f"«{name}»" for name in names) + "."
        if any("outputs" in result.payload for result in results):
            return " Результат — на панели слоёв."
        return ""

    def _push_message(self, text: str, level) -> None:
        self.iface.messageBar().pushMessage(
            "QGIS AI Agent", text, level=level, duration=MESSAGE_DURATION_SEC
        )
