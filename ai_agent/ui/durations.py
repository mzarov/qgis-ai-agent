"""How long something took, as the feed and the settings window write it."""

from ai_agent.i18n import tr

SECONDS = tr("{0} s")
MINUTES = tr("{0} min {1} s")


def format_seconds(seconds: float, decimals: int = 1) -> str:
    """`3.4 s` or `2 min 5 s`; with no decimals the seconds are counted whole, never rounded up."""
    if seconds < 60:
        return SECONDS.format(f"{seconds:.{decimals}f}" if decimals else int(seconds))
    return MINUTES.format(int(seconds // 60), int(seconds % 60))
