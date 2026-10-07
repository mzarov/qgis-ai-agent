"""Rewinding to an earlier message: the conversation, the project, or both, as in Claude Code.

Every applied batch takes a project snapshot first. The orchestrator tags each
new snapshot with the conversation and the user message whose run applied it,
so "before this message" is the earliest snapshot tagged with that message or a
later one. Restoring it also drops every later snapshot: that future is gone.
Snapshots live only as long as QGIS runs and only the newest ten are kept, so
an old message may offer the conversation alone.
"""

from dataclasses import dataclass

from qgis.core import Qgis, QgsMessageLog

from ai_agent.core.orchestrator.notices import (
    LOG_TAG,
    REWIND_BOTH,
    REWIND_CONVERSATION,
    REWIND_PROJECT,
    STATUS_HIDDEN,
    SWITCH_WHILE_RUNNING,
)
from ai_agent.i18n import tr
from ai_agent.qgis_tools.project.restore import restore_snapshot
from ai_agent.qgis_tools.project.snapshots import MAX_SNAPSHOTS, drop_snapshot, last_snapshot, snapshot_exists

REWOUND_CONVERSATION = tr("The conversation is back to before this message; the message is in the box.")
REWOUND_PROJECT = tr("The project is back to how it was before this message.")
UNDONE_PROJECT = tr("The plan is undone: the project is back to how it was before it.")
UNDO_GONE = tr("This plan can no longer be undone: its snapshot is gone (only the latest {0} are kept).")
REWIND_FAILED = tr("Could not restore the project: {0}")
DATA_EDITS_NOTE = tr("Edits written into data sources are not undone.")
EMPTY_LAYERS = tr("These temporary layers came back empty: {0}.")


@dataclass(frozen=True)
class Checkpoint:
    snapshot: str
    session: str
    message: int


class RewindMixin:
    def _note_apply_start(self) -> None:
        self._snapshot_before_apply = last_snapshot()

    def _record_checkpoint(self) -> None:
        """Tag a snapshot the last apply took with the user message whose run applied it."""
        path = last_snapshot()
        if not path or path == getattr(self, "_snapshot_before_apply", ""):
            return
        self._snapshot_before_apply = path
        users = [index for index, message in enumerate(self.conversation.messages) if message.get("role") == "user"]
        if users:
            self._checkpoints.append(Checkpoint(path, self.conversation.session_identifier, users[-1]))

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
        messages = self.conversation.messages
        if not 0 <= message < len(messages) or messages[message].get("role") != "user":
            return
        checkpoint = self.checkpoint_for(message)
        choice = self.dock_widget.choose_rewind(checkpoint is not None)
        if checkpoint is not None and not snapshot_exists(checkpoint.snapshot):
            # The question is modal, but an undo may still have consumed the snapshot meanwhile.
            checkpoint = None
        restored = ""
        if choice in (REWIND_BOTH, REWIND_PROJECT) and checkpoint is not None:
            restored = self._rewind_project(checkpoint)
            if not restored:
                return
        if choice in (REWIND_BOTH, REWIND_CONVERSATION):
            self._rewind_conversation(message)
        # After the conversation replay, which clears the chat, so the note stays visible.
        if restored:
            self.dock_widget.add_system_message(restored)

    def on_undo_plan(self, message_id: int) -> None:
        """Undo one applied plan from the card: restore the snapshot its apply took."""
        if not self.is_idle:
            self.dock_widget.add_system_message(SWITCH_WHILE_RUNNING)
            return
        path = self._plan_snapshots.get(message_id, "")
        if not path or not snapshot_exists(path):
            self.dock_widget.add_system_message(UNDO_GONE.format(MAX_SNAPSHOTS))
            return
        position = next((index for index, item in enumerate(self._checkpoints) if item.snapshot == path), None)
        if position is None:
            checkpoint = Checkpoint(path, self.conversation.session_identifier, len(self.conversation.messages))
            later = [checkpoint]
        else:
            # By the order the applies happened, not by message: the stages of one run share a message,
            # and undoing the second stage must keep the first one's snapshot.
            checkpoint = self._checkpoints[position]
            later = [item for item in self._checkpoints[position:] if item.session == checkpoint.session]
        note = self._rewind_project(checkpoint, UNDONE_PROJECT, later)
        if not note:
            return
        # The project is back to before this plan, so every plan applied after it is gone too.
        gone = {item.snapshot for item in later}
        for plan_id, snapshot in list(self._plan_snapshots.items()):
            if plan_id == message_id or snapshot in gone:
                del self._plan_snapshots[plan_id]
                self.dock_widget.mark_plan_undone(plan_id)
        self.dock_widget.add_system_message(note)
        # The next request starts from the conversation: the model must know the changes are gone.
        self.conversation.add("assistant", UNDONE_PROJECT)

    def _rewind_project(self, checkpoint: Checkpoint, headline: str = "", later: list[Checkpoint] | None = None) -> str:
        """Restore the snapshot and forget the checkpoints it supersedes (`later`, by default every one
        from the checkpoint's message on); returns the note for the chat, or "" after reporting a failure."""
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
            self.dock_widget.add_system_message(REWIND_FAILED.format(failure))
            return ""
        finally:
            self._restoring_snapshot = False
        for item in later:
            if item.snapshot != checkpoint.snapshot:
                drop_snapshot(item.snapshot)
        self._checkpoints = [item for item in self._checkpoints if item not in later]
        self._snapshot_before_apply = last_snapshot()
        # "Done in 7 s" under the restore's note would read as its outcome.
        self.dock_widget.show_outcome(STATUS_HIDDEN)
        notes = [headline or REWOUND_PROJECT, DATA_EDITS_NOTE]
        if result.get("empty_scratch_layers"):
            notes.append(
                tr("These temporary layers came back empty: {0}.").format(", ".join(result["empty_scratch_layers"]))
            )
        QgsMessageLog.logMessage(f"Rewound the project to {checkpoint.snapshot}.", LOG_TAG, Qgis.MessageLevel.Info)
        return " ".join(notes)

    def _rewind_conversation(self, message: int) -> None:
        text = str(self.conversation.messages[message].get("content") or "")
        self._drop_pending_plan()
        self.conversation.truncate(message)
        self._replay()
        self.dock_widget.restore_prompt(text)
        self.dock_widget.add_system_message(REWOUND_CONVERSATION)
