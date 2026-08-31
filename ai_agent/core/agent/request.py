from dataclasses import dataclass
from typing import Any

from ai_agent.core.agent.prompts import (
    build_apply_now_schema,
    build_ask_user_schema,
    build_json_tools_block,
    build_load_skill_schema,
    build_system_prompt,
    build_update_plan_schema,
    render_project_notes,
)
from ai_agent.core.agent.transcript import Transcript
from ai_agent.core.context.project import get_project_context
from ai_agent.core.llm.client import resolve_endpoint
from ai_agent.core.llm.transport import PROTOCOL_JSON, PROTOCOL_NATIVE
from ai_agent.core.privacy import sensitive_data_allowed, tool_output_allowed
from ai_agent.core.settings import (
    get_api_key,
    get_api_url,
    get_auth_type,
    get_dialect,
    get_model,
    get_supports_images,
    get_supports_tools,
    get_verify_ssl,
)
from ai_agent.i18n import locale_code
from ai_agent.qgis_tools.project.notes import NoteStore
from ai_agent.qgis_tools.registry import build_tool_schemas, get_tools_for_skills
from ai_agent.skills.registry import SKILL_REGISTRY

PRIVACY_MODE_PROMPT = (
    "Privacy mode is active. Do not request sampled feature values, selected feature details, "
    "query result rows, or rendered map/layout images. Ask the user to enable sensitive data "
    "sharing in Settings if the task genuinely requires them."
)


@dataclass
class StepRequest:
    messages: list[dict[str, Any]]
    tool_schemas: list[dict[str, Any]]
    overrides: dict[str, Any]
    protocol: str


def build_step_request(
    transcript: Transcript,
    loaded_skills: list[str],
    history: list[dict[str, str]],
    overrides: dict[str, Any] | None = None,
    task_plan: str = "",
    queued_steps: str = "",
) -> StepRequest:
    effective_overrides = dict(overrides) if overrides is not None else build_overrides()
    endpoint = str(effective_overrides.get("url_override") or get_api_url() or "")
    schemas = build_tool_schemas_for(loaded_skills, endpoint)
    json_protocol = detect_json_protocol(effective_overrides)
    system_prompt = build_system_prompt(
        project_context=get_project_context(),
        loaded_skills=loaded_skills,
        json_protocol=json_protocol,
        locale=locale_code(),
        task_plan=task_plan,
        queued_steps=queued_steps,
        project_notes=_project_notes(),
    )
    if json_protocol:
        tools_block = build_json_tools_block(schemas)
        if tools_block:
            system_prompt = f"{system_prompt}\n\n{tools_block}"
    if not sensitive_data_allowed(endpoint):
        system_prompt = f"{system_prompt}\n\n{PRIVACY_MODE_PROMPT}"
    allow_sensitive = sensitive_data_allowed(endpoint)
    return StepRequest(
        messages=transcript.build_messages(
            system_prompt,
            history,
            include_images=not detect_images_unsupported(effective_overrides),
            allow_sensitive=allow_sensitive,
        ),
        tool_schemas=schemas,
        overrides=effective_overrides,
        protocol=PROTOCOL_JSON if json_protocol else PROTOCOL_NATIVE,
    )


def _project_notes() -> str:
    try:
        return render_project_notes(NoteStore().notes())
    except Exception:
        return ""


def build_tool_schemas_for(loaded_skills: list[str], endpoint: str | None = None) -> list[dict[str, Any]]:
    tools = [tool for tool in get_tools_for_skills(loaded_skills) if tool_output_allowed(tool, endpoint)]
    schemas = build_tool_schemas(tools)
    schemas.insert(0, build_apply_now_schema())
    schemas.insert(0, build_ask_user_schema())
    schemas.insert(0, build_update_plan_schema())
    remaining = [name for name in SKILL_REGISTRY.names() if name not in loaded_skills]
    if remaining:
        schemas.insert(0, build_load_skill_schema(remaining))
    return schemas


def detect_images_unsupported(overrides: dict[str, Any] | None = None) -> bool:
    scope = overrides or {}
    try:
        return (
            get_supports_images(
                resolve_endpoint(scope.get("url_override")),
                scope.get("model_override"),
                scope.get("dialect_override"),
            )
            is False
        )
    except Exception:
        return False


def detect_json_protocol(overrides: dict[str, Any] | None = None) -> bool:
    scope = overrides or {}
    try:
        return (
            get_supports_tools(
                resolve_endpoint(scope.get("url_override")),
                scope.get("model_override"),
                scope.get("dialect_override"),
            )
            is False
        )
    except Exception:
        return False


def build_overrides() -> dict[str, Any]:
    return {
        "url_override": get_api_url(),
        "model_override": get_model(),
        "key_override": get_api_key(),
        "auth_type_override": get_auth_type(),
        "dialect_override": get_dialect(),
        "verify_override": get_verify_ssl(),
    }
