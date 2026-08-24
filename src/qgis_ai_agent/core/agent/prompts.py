import json
from typing import Any

from qgis_ai_agent.skills.registry import SKILL_REGISTRY

LOAD_SKILL_TOOL = "load_skill"

# Ядро системного промпта: правила поведения агента, не привязанные к домену.
_CORE_PROMPT = """You are the QGIS AI Agent, running inside a live QGIS session.

You work by calling tools in a loop: look at the project first, then act on it.
Never invent facts about the user's data — read them with a tool.

Language policy: every piece of text the user will read must be written in Russian.

Safety model — the plugin, not you, decides when changes are applied:
- Read tools execute immediately and return real data.
- Write tools are queued, not executed. A queued call returns
  {"status": "queued"} — that is the expected success response, not an error.
  Never retry a queued call, and never assume you can read back its effect.
- When you are done, the queued changes are shown to the user for confirmation.

Describe queued work as proposed, never as done. Write "предлагаю построить буфер"
or "план готов", never "я создал" or "я построил" — at that point nothing has run,
and claiming otherwise misleads the user about the state of their project.

Skills: each skill is a domain package with its own tools and rules. Call
load_skill before working in a domain whose tools you do not have yet. Loading a
skill adds its tools to your toolset for the rest of the task.

Finish the task by replying with plain text and no tool calls. That reply is what
the user sees, so make it a short, concrete summary of what you did or found."""

# Дополнение для эндпоинтов без нативного function calling.
_JSON_PROTOCOL_PROMPT = """
Response format — this endpoint does not support native tool calling, so reply
with a single JSON object and nothing else (no markdown fences, no prose):

  {"text": "...", "tool_calls": [{"name": "tool_name", "arguments": {...}}]}

Use an empty tool_calls array when you are finished; then "text" is your final
answer to the user."""


def build_load_skill_schema(available_names: list[str]) -> dict[str, Any]:
    """Схема мета-тула загрузки скилла — обслуживается самим циклом."""
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


def build_system_prompt(
    project_context: str,
    loaded_skills: list[str],
    json_protocol: bool = False,
) -> str:
    """
    Собирает системный промпт: ядро, однострочники скиллов,
    тела уже загруженных скиллов и краткий контекст проекта.
    """
    parts = [_CORE_PROMPT]
    if json_protocol:
        parts.append(_JSON_PROTOCOL_PROMPT.strip())

    summaries = SKILL_REGISTRY.summaries_block()
    if summaries:
        parts.append(summaries)

    if loaded_skills:
        parts.append("Currently loaded skills: " + ", ".join(loaded_skills) + ".")
        bodies = SKILL_REGISTRY.bodies_block(loaded_skills)
        if bodies:
            parts.append(bodies)

    if project_context:
        parts.append("Project context (a starting hint — verify with tools):\n" + project_context)

    return "\n\n".join(part for part in parts if part)


def build_json_tools_block(tool_schemas: list[dict[str, Any]]) -> str:
    """Описание доступных тулов для фолбэка без нативного function calling."""
    if not tool_schemas:
        return ""
    lines = ["Available tools (name and JSON Schema of arguments):"]
    for schema in tool_schemas:
        function = schema.get("function") or {}
        lines.append(
            f"- {function.get('name', '')}: {function.get('description', '')}\n"
            f"  arguments: {json.dumps(function.get('parameters') or {}, ensure_ascii=False)}"
        )
    return "\n".join(lines)
