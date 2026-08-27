import json
from typing import Any

from qgis_ai_agent.skills.registry import SKILL_REGISTRY

LOAD_SKILL_TOOL = "load_skill"

CORE_PROMPT = """You are the QGIS AI Agent, running inside a live QGIS session.

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

Skills: each skill is a domain package with its own tools and rules. Call
load_skill before working in a domain whose tools you do not have yet. Loading a
skill adds its tools to your toolset for the rest of the task.

Finish the task by replying with plain text and no tool calls. That reply is what
the user sees, so make it a short, concrete summary of what you did or found."""

JSON_PROTOCOL_PROMPT = """Response format — this endpoint does not support native tool calling, so reply
with a single JSON object and nothing else (no markdown fences, no prose):

  {"text": "...", "tool_calls": [{"name": "tool_name", "arguments": {...}}]}

Use an empty tool_calls array when you are finished; then "text" is your final
answer to the user."""

LANGUAGE_POLICY = (
    "Language policy: the QGIS interface here is set to «{language}», so answer in "
    "that language by default. If the user writes to you in a different language, "
    "switch to theirs and stay there — match the person, not the setting. This "
    "applies to everything the user reads; tool names and their arguments stay as "
    "they are documented."
)
LANGUAGE_NAMES = {
    "en": "English",
    "ru": "Russian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "it": "Italian",
    "pl": "Polish",
    "uk": "Ukrainian",
    "zh": "Chinese",
    "ja": "Japanese",
}
PROJECT_CONTEXT_HEADER = "Project context (a starting hint — verify with tools):"
LOADED_SKILLS_HEADER = "Currently loaded skills: "
TOOLS_BLOCK_HEADER = "Available tools (name and JSON Schema of arguments):"


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
    return LANGUAGE_POLICY.format(language=LANGUAGE_NAMES.get(code, code or "English"))


def build_system_prompt(
    project_context: str,
    loaded_skills: list[str],
    json_protocol: bool = False,
    locale: str = "en",
) -> str:
    parts = [CORE_PROMPT, language_policy(locale)]
    if json_protocol:
        parts.append(JSON_PROTOCOL_PROMPT)
    parts.append(SKILL_REGISTRY.summaries_block())
    if loaded_skills:
        parts.append(LOADED_SKILLS_HEADER + ", ".join(loaded_skills) + ".")
        parts.append(SKILL_REGISTRY.bodies_block(loaded_skills))
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
        lines.append(
            f"- {function.get('name', '')}: {function.get('description', '')}\n"
            f"  arguments: {parameters}"
        )
    return "\n".join(lines)
