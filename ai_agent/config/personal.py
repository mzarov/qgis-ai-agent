from dataclasses import dataclass, fields
from typing import Any

from qgis.core import QgsSettings

PREFIX = "ai_agent/personal"
MAX_NAME = 60
MAX_ROLE = 80
MAX_ABOUT = 1500
EXPERIENCE = ("auto", "beginner", "regular", "expert")
UNITS = ("metric", "imperial")
LAYER_NAMES = ("plain", "technical")
STYLES = ("concise", "balanced", "detailed")
QUESTIONS = ("rarely", "when_needed", "often")
AUTO_ANSWER = (0, 60, 180, 300)
PANEL_THEMES = ("auto", "light", "dark")
LANGUAGES = {
    "en": "English",
    "ru": "Russian",
    "uk": "Ukrainian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "pl": "Polish",
    "nl": "Dutch",
    "tr": "Turkish",
    "zh": "Chinese",
    "ja": "Japanese",
}


@dataclass
class Profile:
    name: str = ""
    role: str = ""
    about: str = ""
    experience: str = "auto"
    units: str = "metric"
    layer_names: str = "plain"
    language: str = ""
    style: str = "balanced"
    questions: str = "when_needed"
    auto_answer: int = 0
    explain_after: bool = True
    show_steps: bool = True
    follow_changes: bool = True
    own_notes: bool = True
    panel_theme: str = "auto"


CHOICES: dict[str, tuple[object, ...]] = {
    "experience": EXPERIENCE,
    "units": UNITS,
    "layer_names": LAYER_NAMES,
    "language": ("", *LANGUAGES),
    "style": STYLES,
    "questions": QUESTIONS,
    "auto_answer": AUTO_ANSWER,
    "panel_theme": PANEL_THEMES,
}
LIMITS = {"name": MAX_NAME, "role": MAX_ROLE, "about": MAX_ABOUT}


def load() -> Profile:
    settings = QgsSettings()
    default = Profile()
    values: dict[str, Any] = {}
    for field in fields(Profile):
        fallback = getattr(default, field.name)
        raw = settings.value(f"{PREFIX}/{field.name}", fallback)
        values[field.name] = _clean(field.name, raw, fallback)
    return Profile(**values)


def save(profile: Profile) -> None:
    settings = QgsSettings()
    for field in fields(Profile):
        value = _clean(field.name, getattr(profile, field.name), getattr(Profile(), field.name))
        settings.setValue(f"{PREFIX}/{field.name}", value)


def follows_changes() -> bool:
    return load().follow_changes


def _clean(name: str, raw: object, fallback: object) -> object:
    if not isinstance(raw, (str, int, float, bool)):
        return fallback
    if isinstance(fallback, bool):
        return raw if isinstance(raw, bool) else str(raw).strip().lower() in ("true", "1", "yes")
    if isinstance(fallback, int):
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return fallback
        return number if number in CHOICES.get(name, (number,)) else fallback
    text = str(raw or "").strip()
    if name in CHOICES:
        return text if text in CHOICES[name] else fallback
    return text[: LIMITS.get(name, len(text))]
