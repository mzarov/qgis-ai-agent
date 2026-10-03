"""What the orchestrator says in the chat and the QGIS message bar, in one place."""

from ai_agent.i18n import tr

LOG_TAG = "AI Agent"
MESSAGE_DURATION_SEC = 8
SESSION_MISSING = tr("Conversation not found.")
RUN_STOPPED = tr("Run stopped. Pending work was cancelled.")
APPLY_STOPPED = tr("Run stopped during apply. Pending steps were cancelled; any completed changes remain.")
SWITCH_WHILE_RUNNING = tr("Wait for the current task to finish.")
SWITCH_WHILE_APPLYING = tr("Changes are being applied — wait for that to finish.")
VERIFYING = tr("Checking the applied changes…")
DESTRUCTIVE_DECLINED = tr("Kept everything as it was — the destructive steps were not applied.")
INTERJECTED = tr("Passed to the agent — it will take this into account on its next step.")
PLAN_DROPPED = tr("The planned changes were dropped — they were not applied. Starting over from your message.")
AWAITING_ANSWER = tr("Waiting for your answer — the run continues from it.")
DATA_SHARING_DECLINED = tr("Request not sent.")
UNKNOWN_SKILL = tr("No skill named /{0}. Available: {1}.")
PROJECT_CHANGED = tr("The QGIS project changed. A new project-scoped conversation was started.")
PREVIOUS_APPLY_INTERRUPTED = tr("An interrupted run completed work in the previous project; see its conversation.")
