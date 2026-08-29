from ai_agent.core.llm.client import is_local
from ai_agent.core.settings import get_api_key, get_api_url
from ai_agent.i18n import tr, tr_n


def compact_number(value: int) -> str:
    if value < 1000:
        return str(value)
    return f"{value / 1000:.1f}k"


def where_to_look(results: list) -> str:
    names = [result.payload.get("result_layer_name") for result in results if result.payload.get("result_layer_name")]
    if names:
        return " " + tr("New layers: {0}.").format(", ".join(f"«{name}»" for name in names))
    if any("outputs" in result.payload for result in results):
        return " " + tr("The result is in the layer panel.")
    return ""


def interrupted_outcome(results: list) -> str:
    successful = [result for result in results if result.ok]
    if not successful:
        return ""
    return tr_n(
        "Stopped after %n completed step(s); pending steps were cancelled.{0}",
        len(successful),
    ).format(where_to_look(successful))


def is_configured() -> bool:
    try:
        url = (get_api_url() or "").strip()
        return bool(url) and (bool((get_api_key() or "").strip()) or is_local(url))
    except Exception:
        return False
