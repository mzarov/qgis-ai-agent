from dataclasses import dataclass

from ai_agent.core.llm.dialects import ANTHROPIC, AUTO, OPENAI
from ai_agent.i18n import tr

CUSTOM = tr("Custom address")


@dataclass(frozen=True)
class Preset:
    title: str
    url: str
    dialect: str
    model_hint: str
    needs_key: bool = True

    @property
    def is_custom(self) -> bool:
        return not self.url


PRESETS: list[Preset] = [
    Preset(CUSTOM, "", AUTO, tr("the model name at your provider")),
    Preset("OpenAI", "https://api.openai.com/v1", OPENAI, "gpt-4o"),
    Preset("OpenRouter", "https://openrouter.ai/api/v1", OPENAI, tr("vendor/model")),
    Preset("Anthropic", "https://api.anthropic.com/v1", ANTHROPIC, "claude-sonnet-4-20250514"),
    Preset("DeepSeek", "https://api.deepseek.com/v1", OPENAI, "deepseek-chat"),
    Preset("Groq", "https://api.groq.com/openai/v1", OPENAI, tr("a model name from the Groq console")),
    Preset("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", OPENAI, "gemini-2.5-flash"),
    Preset("Mistral", "https://api.mistral.ai/v1", OPENAI, "mistral-large-latest"),
    Preset("Ollama", "http://localhost:11434/v1", OPENAI, tr("a name from ollama list"), needs_key=False),
    Preset("LM Studio", "http://localhost:1234/v1", OPENAI, tr("a name from LM Studio"), needs_key=False),
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
