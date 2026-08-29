from dataclasses import dataclass

from qgis_ai_agent.core.llm.dialects import ANTHROPIC, AUTO, OPENAI
from qgis_ai_agent.i18n import tr

CUSTOM = tr("Custom address")


@dataclass(frozen=True)
class Preset:
    title: str
    url: str
    dialect: str
    model_hint: str
    default_model: str = ""
    needs_key: bool = True

    @property
    def is_custom(self) -> bool:
        return not self.url


PRESETS: list[Preset] = [
    Preset(CUSTOM, "", AUTO, tr("the model name at your provider")),
    Preset("OpenAI", "https://api.openai.com/v1", OPENAI, "gpt-4o-mini", "gpt-4o-mini"),
    Preset("OpenRouter", "https://openrouter.ai/api/v1", OPENAI, tr("vendor/model"), "openai/gpt-4o-mini"),
    Preset(
        "Anthropic",
        "https://api.anthropic.com/v1",
        ANTHROPIC,
        "claude-sonnet-5",
        "claude-sonnet-5",
    ),
    Preset("DeepSeek", "https://api.deepseek.com/v1", OPENAI, "deepseek-v4-pro", "deepseek-v4-pro"),
    Preset(
        "Groq",
        "https://api.groq.com/openai/v1",
        OPENAI,
        tr("a model name from the Groq console"),
        "openai/gpt-oss-120b",
    ),
    Preset("Mistral", "https://api.mistral.ai/v1", OPENAI, "mistral-large-latest", "mistral-large-latest"),
    Preset(
        "Ollama",
        "http://localhost:11434/v1",
        OPENAI,
        tr("a name from ollama list"),
        "llama3.2",
        needs_key=False,
    ),
    Preset(
        "LM Studio",
        "http://localhost:1234/v1",
        OPENAI,
        tr("a name from LM Studio"),
        needs_key=False,
    ),
]

TITLES = [preset.title for preset in PRESETS]


def by_title(title: str) -> Preset:
    for preset in PRESETS:
        if preset.title == title:
            return preset
    return PRESETS[0]


def matching(url: str) -> Preset:
    wanted = (url or "").strip().rstrip("/").lower()
    for preset in PRESETS:
        if preset.url and preset.url.lower() == wanted:
            return preset
    return PRESETS[0]
