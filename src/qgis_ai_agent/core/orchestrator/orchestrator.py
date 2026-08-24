import json
from typing import Any

from qgis.core import Qgis, QgsMessageLog

from qgis_ai_agent.core.context.project import get_project_context
from qgis_ai_agent.core.execution.service import ExecutionService
from qgis_ai_agent.core.llm.worker import LLMWorkerThread
from qgis_ai_agent.core.orchestrator.contracts import DockWidgetContract
from qgis_ai_agent.core.orchestrator.session import SessionState
from qgis_ai_agent.core.planning.service import PlanService
from qgis_ai_agent.core.settings import (
    get_api_key,
    get_api_url,
    get_auth_type,
    get_model,
    get_verify_ssl,
)
from qgis_ai_agent.core.state.history import HistoryStore
from qgis_ai_agent.qgis_tools.registry import format_steps_for_display


class CoreOrchestrator:
    """Оркестратор диалога, планирования и исполнения шагов."""

    def __init__(self, iface: Any, dock_widget: DockWidgetContract):
        self.iface = iface
        self.dock_widget = dock_widget
        self.state = SessionState()
        self.current_llm_thread = None

        self.history_store = HistoryStore(max_messages=14)
        self.plan_service = PlanService()
        self.execution_service = ExecutionService()

    def on_prompt(self, prompt: str) -> None:
        if not prompt.strip():
            self.iface.messageBar().pushWarning("QGIS AI Agent", "Введите описание макета.")
            return

        self.dock_widget.add_user_message(prompt)
        self.history_store.add("user", prompt)
        self.dock_widget.prompt_edit.clear()

        if self.state.pending_clarification:
            clarification_ctx = self.state.pending_clarification
            data = clarification_ctx.get("data") or {}
            updated = self.plan_service.apply_clarification_answer(data, prompt)
            remaining = updated.get("clarification_questions") or []
            if remaining:
                self.state.pending_clarification["data"] = updated
                self.dock_widget.add_system_message(remaining[0].get("question", "Уточните, пожалуйста."))
                return
            self.state.pending_clarification = None
            self._present_plan(updated, raw_reply=clarification_ctx.get("raw", ""))
            return

        was_pending_plan = bool(self.state.pending_plan and self.state.pending_plan.get("steps"))
        prompt_for_model = prompt
        if was_pending_plan:
            prompt_for_model = self._build_pending_plan_followup_prompt(prompt)

        self.dock_widget.set_busy(True)
        self.state.stream_message_id = self.dock_widget.start_model_stream()
        if not was_pending_plan:
            self.state.plan_message_id = None
        self.state.active_mode = "model_driven"

        project_context = get_project_context()
        history = self.history_store.get()
        messages = self.plan_service.build_messages(prompt_for_model, project_context, history)

        overrides = {
            "url_override": get_api_url(),
            "model_override": get_model(),
            "key_override": get_api_key(),
            "auth_type_override": get_auth_type(),
            "verify_override": get_verify_ssl(),
        }
        payload = {"messages": messages, "overrides": overrides, "stream": True}
        QgsMessageLog.logMessage("Запрос к LLM отправлен в фоне.", "QGIS AI Agent", Qgis.Info)
        self.current_llm_thread = LLMWorkerThread(payload)
        self.current_llm_thread.finished.connect(self.on_llm_finished)
        self.current_llm_thread.error.connect(self.on_llm_error)
        self.current_llm_thread.progress.connect(self.on_llm_progress)
        self.current_llm_thread.start()

    def on_llm_progress(self, chunk: str) -> None:
        if self.state.stream_message_id is not None:
            self.dock_widget.append_model_chunk(self.state.stream_message_id, chunk)

    def on_llm_finished(self, reply: str) -> None:
        self.dock_widget.set_busy(False)
        raw = (reply or "").strip()
        if not raw:
            if self.state.stream_message_id is not None:
                self.dock_widget.finalize_model_message(self.state.stream_message_id, "Ответ модели пуст.")
            self.dock_widget.add_system_message("Получен пустой ответ от API. Проверьте настройки или попробуйте снова.")
            self.state.stream_message_id = None
            return

        try:
            data = self.plan_service.parse_response(raw)
            can_do = data.get("can_do", True)
            next_stage = (data.get("next_stage") or "").strip().lower()
            preface = (data.get("preface") or "").strip()
            message = (data.get("message") or "").strip()
            chat_reply = (data.get("chat_reply") or "").strip()
            plan_description = (data.get("plan_description") or "").strip()

            if next_stage == "chat":
                final_chat = (chat_reply or message or preface).strip()
                if self.state.stream_message_id is not None:
                    self.dock_widget.finalize_model_message(
                        self.state.stream_message_id,
                        final_chat or "Готова помочь.",
                    )
                elif final_chat:
                    self.dock_widget.add_system_message(final_chat)
                if final_chat:
                    self.history_store.add("assistant", final_chat)
                self.state.pending_plan = None
                self.state.stream_message_id = None
                return

            if self.state.stream_message_id is not None:
                preface_text = preface or "Поняла задачу."
                self.dock_widget.finalize_model_message(self.state.stream_message_id, preface_text)
                self.history_store.add("assistant", preface_text)

            if next_stage == "execute":
                self._execute_pending_plan()
                self.state.stream_message_id = None
                return

            if not can_do and next_stage != "plan":
                self.state.pending_plan = None
                self.dock_widget.add_result_message(
                    message or "К сожалению, я пока не научилась это сделать. Попробуйте позже."
                )
                self.state.stream_message_id = None
                return

            clarification_questions = data.get("clarification_questions") or []
            if clarification_questions:
                self.state.pending_clarification = {"raw": raw, "data": data}
                self.state.pending_plan = None
                self.dock_widget.add_system_message(clarification_questions[0].get("question", "Уточните, пожалуйста."))
            else:
                self._present_plan(data, raw_reply=raw, plan_description=plan_description)
        except json.JSONDecodeError as err:
            self.state.pending_plan = None
            if self.state.stream_message_id is not None:
                self.dock_widget.finalize_model_message(
                    self.state.stream_message_id,
                    raw[:500] + ("…" if len(raw) > 500 else ""),
                )
            self.dock_widget.add_result_message(raw[:800])
            self.history_store.add("assistant", raw[:800])
            self.iface.messageBar().pushWarning(
                "QGIS AI Agent",
                f"LLM вернул не-JSON, использован fallback: {err}",
            )
        except Exception as err:
            self.state.pending_plan = None
            if self.state.stream_message_id is not None:
                self.dock_widget.finalize_model_message(self.state.stream_message_id, "")
            self.dock_widget.add_system_message(f"Ошибка: {err}")
            self.iface.messageBar().pushCritical("QGIS AI Agent", str(err))
        self.state.stream_message_id = None

    def on_confirm_plan(self) -> None:
        self._execute_pending_plan()

    def on_cancel_plan(self) -> None:
        self.state.pending_plan = None
        self.state.plan_message_id = None
        self.state.pending_clarification = None
        self.dock_widget.add_system_message("План отменён.")

    def on_llm_error(self, err: str) -> None:
        self.dock_widget.set_busy(False)
        if self.state.stream_message_id is not None:
            self.dock_widget.finalize_model_message(self.state.stream_message_id, "")
        self.state.stream_message_id = None
        self.state.last_error = err
        self.dock_widget.add_system_message(f"Ошибка запроса: {err}")
        self.iface.messageBar().pushCritical("QGIS AI Agent", err)

    def _build_pending_plan_followup_prompt(self, user_update: str) -> str:
        if not self.state.pending_plan:
            return user_update
        old_steps = self.state.pending_plan.get("steps") or []
        old_lines = format_steps_for_display(old_steps)
        old_plan = "\n".join(old_lines) if old_lines else "(пусто)"
        return (
            "У тебя уже есть предложенный план ниже. "
            "По сообщению пользователя определи следующий этап:\n"
            "- next_stage=execute, если пользователь подтверждает выполнение текущего плана;\n"
            "- next_stage=plan, если пользователь вносит правки и нужен новый план;\n"
            "- next_stage=chat, если это обычный вопрос/диалог.\n\n"
            f"Текущий план:\n{old_plan}\n\n"
            f"Сообщение пользователя:\n{user_update}"
        )

    def _execute_pending_plan(self) -> None:
        """Выполняет текущий pending plan, если он есть."""
        if not self.state.pending_plan or not self.state.pending_plan.get("steps"):
            self.state.pending_plan = None
            self.state.pending_clarification = None
            self.dock_widget.add_system_message("Нет плана для выполнения. Сначала сформируйте план.")
            return

        steps = self.state.pending_plan["steps"]
        self.state.pending_plan = None
        try:
            last_name = self.execution_service.execute_steps(steps)
            if last_name:
                QgsMessageLog.logMessage(
                    f"Макет «{last_name}» создан/обновлён, шагов: {len(steps)}.",
                    "QGIS AI Agent",
                    Qgis.Info,
                )
                if self.state.plan_message_id is not None:
                    self.dock_widget.mark_plan_completed(self.state.plan_message_id)
                self.dock_widget.add_result_message(
                    f"Макет «{last_name}» создан или обновлён. Проект → Менеджер макетов."
                )
                self.iface.messageBar().pushSuccess("QGIS AI Agent", f"Макет «{last_name}» готов.")
            else:
                self.dock_widget.add_system_message("Выполнение завершено без изменений.")
            self.state.plan_message_id = None
        except Exception as err:
            self.dock_widget.add_system_message(f"Ошибка выполнения: {err}")
            self.iface.messageBar().pushCritical("QGIS AI Agent", str(err))

    def _present_plan(self, data: dict, raw_reply: str, plan_description: str = "") -> None:
        """Показывает план, если есть исполнимые шаги."""
        steps = data.get("steps") or []
        plan_lines = format_steps_for_display(steps) if steps else [
            line.strip() for line in (plan_description or "").splitlines() if line.strip()
        ]
        if steps:
            self.state.plan_message_id = self.dock_widget.add_plan_message(plan_lines)
            self.state.pending_plan = {"raw": raw_reply, "data": data, "steps": steps}
            self.dock_widget.add_system_message(
                f"План из {len(steps)} шагов. Напишите в чат «подтверждаю» для выполнения, "
                f"или пришлите правки, чтобы перестроить план."
            )
        else:
            self.state.pending_plan = None
            self.dock_widget.add_system_message(
                "Модель не вернула шагов для выполнения. Уточните запрос или попробуйте снова."
            )
