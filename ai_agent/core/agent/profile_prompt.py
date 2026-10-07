"""The Personalisation settings as the model reads them: who the user is and how they want the work done.

Rendered into the static system prompt, after the language policy: it changes
only when the user saves Settings, so the cached prefix holds from turn to turn.
Defaults say nothing — a profile left as it is adds no tokens.
"""

from ai_agent.config.personal import LANGUAGES, Profile

PROFILE_HEADER = "## The user and how they like to work (from their Settings)"
EXPERIENCE = {
    "beginner": "They are new to GIS: explain terms briefly, prefer the simple method, say what each step does.",
    "regular": "They use GIS regularly: explain only what is unusual.",
    "expert": "They are a GIS expert: skip explanations of standard concepts, be precise and technical.",
}
UNITS = {
    "imperial": "Report distances, areas and speeds in imperial units (feet, miles, acres), "
    "converting from the layer's units where needed.",
}
LAYER_NAMES = {
    "technical": "Name new layers computer-style: lower case, snake_case, no spaces or accents.",
}
STYLES = {
    "concise": "Keep answers short: the result and what matters, no walkthrough.",
    "detailed": "Give full answers: the result, how you got it and what to watch out for.",
}
QUESTIONS = {
    "rarely": "Ask the user only when you truly cannot choose; otherwise pick the sensible option and say which.",
    "often": "When a choice is the user's to make — classes, colours, extents — ask before acting.",
}
QUIET_AFTER = "After a run, do not add a summary of the changes; the plan card already shows them."
LANGUAGE_OVERRIDE = (
    "Answer language: the user chose {language} in Settings. Write everything they read in {language}, "
    "whatever the QGIS language, unless they write to you in another language."
)


def render_profile(profile: Profile) -> str:
    """The profile block for the system prompt, or "" when nothing differs from the defaults."""
    lines = []
    if profile.name:
        lines.append(f"Address the user as {profile.name}.")
    if profile.role:
        lines.append(f"Their work: {profile.role}. Reach first for the data and methods that work calls for.")
    if profile.about:
        lines.append("About them, in their words:\n" + profile.about)
    for table, key in (
        (EXPERIENCE, profile.experience),
        (UNITS, profile.units),
        (LAYER_NAMES, profile.layer_names),
        (STYLES, profile.style),
        (QUESTIONS, profile.questions),
    ):
        if key in table:
            lines.append(table[key])
    if not profile.explain_after:
        lines.append(QUIET_AFTER)
    if profile.language in LANGUAGES:
        lines.append(LANGUAGE_OVERRIDE.format(language=LANGUAGES[profile.language]))
    return "\n".join([PROFILE_HEADER, *lines]) if lines else ""
