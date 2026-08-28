from dataclasses import dataclass
from typing import Any

from qgis_ai_agent.core.agent.prompts import (
    build_apply_now_schema,
    build_json_tools_block,
    build_load_skill_schema,
    build_system_prompt,
    build_update_plan_schema,
    render_project_notes,
)
from qgis_ai_agent.core.agent.transcript import Transcript
from qgis_ai_agent.core.context.project import get_project_context
from qgis_ai_agent.core.llm.client import resolve_endpoint
from qgis_ai_agent.core.llm.transport import PROTOCOL_JSON, PROTOCOL_NATIVE
from qgis_ai_agent.core.settings import (
    get_api_key,
    get_api_url,
    get_auth_type,
    get_model,
    get_supports_images,
    get_supports_tools,
    get_verify_ssl,
)
from qgis_ai_agent.i18n import locale_code
from qgis_ai_agent.qgis_tools.project.notes import NoteStore
from qgis_ai_agent.qgis_tools.registry import build_tool_schemas, get_tools_for_skills
from qgis_ai_agent.skills.registry import SKILL_REGISTRY


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
) -> StepRequest:
    schemas = build_tool_schemas_for(loaded_skills)
    json_protocol = detect_json_protocol()
    system_prompt = build_system_prompt(
        project_context=get_project_context(),
        loaded_skills=loaded_skills,
        json_protocol=json_protocol,
        locale=locale_code(),
        task_plan=task_plan,
        project_notes=_project_notes(),
    )
    if json_protocol:
        tools_block = build_json_tools_block(schemas)
        if tools_block:
            system_prompt = f"{system_prompt}\n\n{tools_block}"
    return StepRequest(
        messages=transcript.build_messages(system_prompt, history, include_images=not detect_images_unsupported()),
        tool_schemas=schemas,
        overrides=overrides if overrides is not None else build_overrides(),
        protocol=PROTOCOL_JSON if json_protocol else PROTOCOL_NATIVE,
    )


def _project_notes() -> str:
    try:
        return render_project_notes(NoteStore().notes())
    except Exception:
        return ""


def build_tool_schemas_for(loaded_skills: list[str]) -> list[dict[str, Any]]:
    schemas = build_tool_schemas(get_tools_for_skills(loaded_skills))
    schemas.insert(0, build_apply_now_schema())
    schemas.insert(0, build_update_plan_schema())
    remaining = [name for name in SKILL_REGISTRY.names() if name not in loaded_skills]
    if remaining:
        schemas.insert(0, build_load_skill_schema(remaining))
    return schemas


def detect_images_unsupported() -> bool:
    try:
        return get_supports_images(resolve_endpoint()) is False
    except Exception:
        return False


def detect_json_protocol() -> bool:
    try:
        return get_supports_tools(resolve_endpoint()) is False
    except Exception:
        return False


def build_overrides() -> dict[str, Any]:
    return {
        "url_override": get_api_url(),
        "model_override": get_model(),
        "key_override": get_api_key(),
        "auth_type_override": get_auth_type(),
        "verify_override": get_verify_ssl(),
    }
