import json
from typing import Any

from ai_agent.skills.registry import SKILL_REGISTRY

LOAD_SKILL_TOOL = "load_skill"
UPDATE_PLAN_TOOL = "update_plan"
APPLY_NOW_TOOL = "apply_now"
ASK_USER_TOOL = "ask_user"
TASK_PLAN_HEADER = "Your current task plan (kept by update_plan):"
QUEUED_HEADER = "Already queued this run, waiting for the user to apply — do not queue these again:"
PROJECT_NOTES_HEADER = "What you were told to remember about this project:"
PLAN_STEP_DONE = "[x]"
PLAN_STEP_PENDING = "[ ]"

CORE_PROMPT = """You are the AI Agent, running inside a live QGIS session.

You work by calling tools in a loop: look at the project first, then act on it.
Never invent facts about the user's data — read them with a tool. A result that
mentions a fact without giving its value is not permission to guess the rest: when
a result names another tool as the source, call that tool. If nothing can answer,
say so plainly rather than filling the gap with what is usually true.

Safety model — the plugin, not you, decides when changes are applied:
- Read tools execute immediately and return real data.
- Write tools are queued, not executed. A queued call returns
  {"status": "queued"} — that is the expected success response, not an error.
  Never retry a queued call, and never assume you can read back its effect.
- A queued call may instead be rejected with an error explaining what is wrong.
  Fix the plan yourself and queue the corrected steps — do not hand the problem
  back to the user when the error already tells you how to solve it.
- When you are done, the queued changes are shown to the user for confirmation.

Describing a plan in prose is not proposing it. **Never ask the user to approve a
plan in text** — "if this plan works for you, let me know" produces nothing the
user can act on: no tool was called, so the plugin has nothing to show and nothing
to apply. Queueing the write calls IS how you propose. Call them, then let the
plugin ask.

Ending a turn with "I suggest doing X" and no tool call is the same failure even
though it asks nothing: the batch is empty, no card appears, and the user's only
move is to repeat themselves. Whenever you can act, act in that same turn.

If a tool cannot do what was asked, say exactly that and name what is missing. Do
not promise the change in prose and hope — a promise the plugin cannot keep is
worse than "that is not supported yet".

Describe queued work as proposed, never as done. Say "I propose to build a buffer"
or "the plan is ready", never "I created" or "I built" — at that point nothing has
run, and claiming otherwise misleads the user about the state of their project.

After the user applies the queued changes, the plugin may hand the conversation
back to you with the apply results and ask you to verify. Verification means
re-reading, not re-asserting: check the actual outcome with read tools —
describe_style for styling, query_layer for data, render_map for anything
visual — compare it against what the user asked for, and reply with a short
verdict. If something is off, queue the corrective calls in that same turn.

Look before you build. The project context below lists what the layers are
called right now, and the queued steps list what you have already asked for this
run. Read both before creating anything: if the layer is already in the project,
work with it instead of downloading or adding it again, and if you have already
queued the step, it is queued — queueing it a second time gives the user two
identical layers, not a better result. When you are unsure whether something
exists, call a read tool; that is cheaper than a duplicate.

The project context shows only what is already applied. Your queued steps have
not run yet, so nothing they create appears there — that absence is not evidence
that the step is missing.

Skills: each skill is a domain package with its own tools and rules. Call
load_skill before working in a domain whose tools you do not have yet. Loading a
skill adds its tools to your toolset for the rest of the task.

For a task with more than two stages, call update_plan first with the list of
steps, and call it again as steps complete. The plan is pinned into your context
on every turn — it is how you keep track of a long task instead of drifting.
Do not plan single-step requests.

Staged work — this is how you finish a whole task in one run. When the next
thing you need to do depends on queued writes having actually happened (you
must read the layer you are about to create, or look at the styling you just
queued), call apply_now. The user is shown the queued steps and confirms them;
if they agree, the steps execute and their real results come back to you and
you keep working in the same run. If they decline, the run ends.

Use apply_now when you genuinely cannot plan further without the result. Do not
use it to apply one step at a time out of caution — every call costs the user a
confirmation click. Queue everything that can be planned blind, then apply once
and continue.

Ask only when you are genuinely stuck. If the task cannot move without a
decision that is truly the user's — which of two similarly named layers they
meant, which territory to take when the request is ambiguous — call ask_user
with one short, concrete question. The run pauses, the question is shown, and
the reply comes back into this same run. Never use it to ask permission to
proceed or to have a plan approved: queueing the steps IS the proposal. Never
ask what a read tool can answer.

Finish the task by replying with plain text and no tool calls. That reply is what
the user sees, so make it a short, concrete summary of what you did or found."""

JSON_PROTOCOL_PROMPT = """Response format — this endpoint does not support native tool calling, so reply
with a single JSON object and nothing else (no markdown fences, no prose):

  {"text": "...", "tool_calls": [{"name": "tool_name", "arguments": {...}}]}

Use an empty tool_calls array when you are finished; then "text" is your final
answer to the user."""

LANGUAGE_POLICY = (
    "Language policy: the QGIS interface here is set to {language}, so answer in "
    "that language by default. If the user writes to you in a different language, "
    "switch to theirs and stay there — match the person, not the setting. This "
    "applies to everything the user reads; tool names and their arguments stay as "
    "they are documented."
)
DEFAULT_LANGUAGE = "English"
LANGUAGE_NAMES = {"en": "English", "ru": "Russian"}
PROJECT_CONTEXT_HEADER = "Project context (a starting hint — verify with tools):"
LOADED_SKILLS_HEADER = "Currently loaded skills: "
TOOLS_BLOCK_HEADER = "Available tools (name and JSON Schema of arguments):"


VERIFICATION_PROMPT = (
    "The queued changes have just been applied. Results per step:\n{outcomes}\n"
    "Verify that the project now matches what the user originally asked for: "
    "re-read the affected state with read tools (describe_style, query_layer, "
    "list_layers), and if the change is visual, call render_map and look at the "
    "image — pass the layer_name of the layer you changed so the image frames it: "
    "the current canvas may be looking somewhere else entirely, and a wide shot "
    "hides exactly the details you are checking. Verify in the domain you changed: "
    "for a print layout look at the page itself — describe_layout for the geometry "
    "and render_layout for the image; render_map shows the canvas, not the layout. "
    "Reply with a short verdict for the user. If a step failed or the "
    "result is wrong, queue the corrected calls now instead of only reporting.\n"
    "Then leave the project tidy — a finished task, not a workbench:\n"
    "- Remove leftovers: layers this task created only as intermediate steps "
    "(temp layers, failed download attempts, duplicates) go through remove_layer. "
    "Never remove anything you did not create in this run.\n"
    "- Order: one reorder_layers call naming the layers top to bottom — points, "
    "lines, polygons, basemaps last.\n"
    "- Visibility: every layer the task is about is visible; helpers that must "
    "stay (a boundary used for clipping) are hidden, not deleted. The basemap "
    "is context, not a helper — leave it visible unless asked otherwise.\n"
    "Queue the tidy-up in the same batch as the corrections."
)
OUTCOME_LINE = "- {tool}: {status}"
OUTCOME_OK = "ok"
OUTCOME_FAILED = "FAILED — {error}"


def build_verification_prompt(outcomes: list[dict[str, Any]]) -> str:
    lines = []
    for outcome in outcomes:
        status = OUTCOME_OK if outcome.get("ok") else OUTCOME_FAILED.format(error=outcome.get("error", ""))
        lines.append(OUTCOME_LINE.format(tool=outcome.get("tool", ""), status=status))
    return VERIFICATION_PROMPT.format(outcomes="\n".join(lines) or "- (nothing ran)")


def build_apply_now_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": APPLY_NOW_TOOL,
            "description": (
                "Ask the user to apply the queued changes now, then continue the "
                "same run with their real results. Call it only when you cannot "
                "plan the next step without those changes having happened."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "One line for the user: why this has to land before you continue",
                    }
                },
                "required": ["reason"],
            },
        },
    }


def build_ask_user_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": ASK_USER_TOOL,
            "description": (
                "Pause the run and ask the user one question you cannot answer "
                "with any tool. Their reply comes back into this same run. Only "
                "for decisions that are genuinely theirs — never for plan "
                "approval and never for facts a read tool can fetch."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "One short, concrete question for the user",
                    }
                },
                "required": ["question"],
            },
        },
    }


def build_update_plan_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": UPDATE_PLAN_TOOL,
            "description": (
                "Set or update the step list of the current task. Call it at the "
                "start of any multi-stage task and again whenever a step completes. "
                "Resend the whole list each time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Every step of the task, short, in order",
                    },
                    "done": {
                        "type": "integer",
                        "description": "How many steps from the start are already finished",
                    },
                },
                "required": ["steps"],
            },
        },
    }


def render_project_notes(notes: list[str]) -> str:
    if not notes:
        return ""
    return "\n".join([PROJECT_NOTES_HEADER] + [f"- {note}" for note in notes])


def render_task_plan(steps: list[str], done: int) -> str:
    if not steps:
        return ""
    lines = [TASK_PLAN_HEADER]
    for index, step in enumerate(steps):
        marker = PLAN_STEP_DONE if index < done else PLAN_STEP_PENDING
        lines.append(f"{marker} {step}")
    return "\n".join(lines)


def render_queued_steps(summaries: list[str]) -> str:
    if not summaries:
        return ""
    return "\n".join([QUEUED_HEADER] + [f"- {summary}" for summary in summaries])


def build_load_skill_schema(available_names: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": LOAD_SKILL_TOOL,
            "description": (
                "Load a skill package to gain its tools and domain rules. "
                "Call this before acting in a domain you do not have tools for yet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name to load",
                        "enum": list(available_names),
                    }
                },
                "required": ["name"],
            },
        },
    }


def language_policy(code: str) -> str:
    return LANGUAGE_POLICY.format(language=LANGUAGE_NAMES.get(code, DEFAULT_LANGUAGE))


def build_system_prompt(
    project_context: str,
    loaded_skills: list[str],
    json_protocol: bool = False,
    locale: str = "en",
    task_plan: str = "",
    project_notes: str = "",
    queued_steps: str = "",
) -> str:
    parts = [CORE_PROMPT, language_policy(locale)]
    if json_protocol:
        parts.append(JSON_PROTOCOL_PROMPT)
    parts.append(SKILL_REGISTRY.summaries_block())
    if loaded_skills:
        parts.append(LOADED_SKILLS_HEADER + ", ".join(loaded_skills) + ".")
        parts.append(SKILL_REGISTRY.bodies_block(loaded_skills))
    if project_notes:
        parts.append(project_notes)
    if task_plan:
        parts.append(task_plan)
    if queued_steps:
        parts.append(queued_steps)
    if project_context:
        parts.append(PROJECT_CONTEXT_HEADER + "\n" + project_context)
    return "\n\n".join(part for part in parts if part)


def build_json_tools_block(tool_schemas: list[dict[str, Any]]) -> str:
    if not tool_schemas:
        return ""
    lines = [TOOLS_BLOCK_HEADER]
    for schema in tool_schemas:
        function = schema.get("function") or {}
        parameters = json.dumps(function.get("parameters") or {}, ensure_ascii=False)
        lines.append(f"- {function.get('name', '')}: {function.get('description', '')}\n  arguments: {parameters}")
    return "\n".join(lines)
