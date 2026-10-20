from dataclasses import dataclass

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.orchestrator.contracts import OrchestratorHost
from ai_agent.core.orchestrator.notices import (
    LOG_TAG,
    REWIND_BOTH,
    REWIND_CONVERSATION,
    REWIND_PROJECT,
    STATUS_HIDDEN,
    SWITCH_WHILE_RUNNING,
)
from ai_agent.core.state.trace import UNDONE
from ai_agent.i18n import tr
from ai_agent.qgis_tools.project.restore import restore_snapshot
from ai_agent.qgis_tools.project.snapshots import MAX_SNAPSHOTS, drop_snapshot, last_snapshot, snapshot_exists

REWOUND_CONVERSATION = tr("The conversation is back to before this message; the message is in the box.")
REWOUND_PROJECT = tr("The project is back to how it was before this message.")
UNDONE_PROJECT = tr("The plan is undone: the project is back to how it was before it.")
UNDO_GONE = tr("This plan can no longer be undone: its snapshot is gone (only the latest {0} are kept).")
REWIND_FAILED = tr("Could not restore the project: {0}")
SNAPSHOT_GONE = tr("The project snapshot for this message is gone, so the project was not rewound.")
DATA_EDITS_NOTE = tr("Edits written into data sources are not undone.")


@dataclass(frozen=True)
class Checkpoint:
    snapshot: str
    session: str
    message: int


class RewindMixin(OrchestratorHost):
    def _note_apply_start(self) -> None:
        self._snapshot_before_apply = last_snapshot()

    def _record_checkpoint(self) -> None:
        path = last_snapshot()
        if not path or path == getattr(self, "_snapshot_before_apply", ""):
            return
        self._snapshot_before_apply = path
        place = self.conversation.last_place("user")
        if place is not None:
            self._checkpoints.append(Checkpoint(path, self.conversation.session_identifier, place))

    def checkpoint_for(self, message: int) -> Checkpoint | None:
        session = self.conversation.session_identifier
        live = [item for item in self._checkpoints if item.session == session and snapshot_exists(item.snapshot)]
        later = [item for item in live if item.message >= message]
        return later[0] if later else None

    def on_rewind(self, message: int) -> None:
        busy = self.agent.is_running or bool(getattr(self.agent, "is_applying", False)) or self.compaction.is_running
        if busy:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        target = self.conversation.message_at(message)
        if target is None or target.get("role") != "user":
            return
        checkpoint = self.checkpoint_for(message)
        choice = self.dock_widget.choose_rewind(checkpoint is not None)
        if checkpoint is not None and not snapshot_exists(checkpoint.snapshot):
            # The question is modal, but an undo may still have consumed the snapshot meanwhile.
            checkpoint = None
            restored = SNAPSHOT_GONE if choice in (REWIND_BOTH, REWIND_PROJECT) else ""
        else:
            restored = ""
        if choice in (REWIND_BOTH, REWIND_PROJECT) and checkpoint is not None:
            restored = self._rewind_project(checkpoint)
            if not restored:
                return
        if choice in (REWIND_BOTH, REWIND_CONVERSATION):
            self._rewind_conversation(message)
        if restored:
            self.dock_widget.add_system_message(restored)

    def on_undo_plan(self, message_id: int) -> None:
        if not self.is_idle:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        # A plan cancelled after this one was meant for the project as it was: it cannot come back.
        self._forget_restore()
        path = self._plan_snapshots.get(message_id, "")
        if not path or not snapshot_exists(path):
            self.dock_widget.add_system_message(UNDO_GONE.format(MAX_SNAPSHOTS))
            return
        position = next((index for index, item in enumerate(self._checkpoints) if item.snapshot == path), None)
        if position is None:
            checkpoint = Checkpoint(path, self.conversation.session_identifier, self.conversation.next_place)
            later = [checkpoint]
        else:
            # By apply order, not message: a run's stages share one, and undoing the second keeps the first.
            checkpoint = self._checkpoints[position]
            later = [item for item in self._checkpoints[position:] if item.session == checkpoint.session]
        note = self._rewind_project(checkpoint, UNDONE_PROJECT, later)
        if not note:
            return
        gone = {item.snapshot for item in later}
        for plan_id, snapshot in list(self._plan_snapshots.items()):
            if plan_id == message_id or snapshot in gone:
                del self._plan_snapshots[plan_id]
                self.dock_widget.mark_plan_undone(plan_id)
                self._plan_settled(UNDONE, plan_id=plan_id)
        self.dock_widget.add_system_message(note)
        self.conversation.add("assistant", UNDONE_PROJECT)

    def _rewind_project(self, checkpoint: Checkpoint, headline: str = "", later: list[Checkpoint] | None = None) -> str:
        if later is None:
            later = [
                item
                for item in self._checkpoints
                if item.session == checkpoint.session and item.message >= checkpoint.message
            ]
        self._restoring_snapshot = True
        try:
            result = restore_snapshot(checkpoint.snapshot)
        except Exception as failure:
            self.dock_widget.add_error_message(REWIND_FAILED.format(failure))
            return ""
        finally:
            self._restoring_snapshot = False
        for item in later:
            if item.snapshot != checkpoint.snapshot:
                drop_snapshot(item.snapshot)
        self._checkpoints = [item for item in self._checkpoints if item not in later]
        self._snapshot_before_apply = last_snapshot()
        self.dock_widget.show_outcome(STATUS_HIDDEN)
        notes = [headline or REWOUND_PROJECT, DATA_EDITS_NOTE]
        if result.get("empty_scratch_layers"):
            notes.append(
                tr("These temporary layers came back empty: {0}.").format(", ".join(result["empty_scratch_layers"]))
            )
        QgsMessageLog.logMessage(f"Rewound the project to {checkpoint.snapshot}.", LOG_TAG, Qgis.MessageLevel.Info)
        return " ".join(notes)

    def _rewind_conversation(self, message: int) -> None:
        target = self.conversation.message_at(message)
        text = str(target.get("content") or "") if target is not None else ""
        if self.agent.is_awaiting_answer:
            self.agent.abort()
        self._drop_pending_plan()
        session = self.conversation.session_identifier
        # A message sent again takes the same place: a checkpoint left here would restore the project too far back.
        self._checkpoints = [item for item in self._checkpoints if item.session != session or item.message < message]
        self.conversation.truncate(message)
        self._replay()
        self.dock_widget.restore_prompt(text)
        self.dock_widget.add_system_message(REWOUND_CONVERSATION)
