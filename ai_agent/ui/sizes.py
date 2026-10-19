from qgis.PyQt.QtCore import QLocale

from ai_agent.i18n import tr

BYTES_IN_MB = 1024 * 1024
BYTES_IN_KB = 1024
MEGABYTES = tr("{0} MB")
KILOBYTES = tr("{0} KB")


def format_bytes(size: int) -> str:
    locale = QLocale()
    if size >= BYTES_IN_MB:
        return MEGABYTES.format(locale.toString(size / BYTES_IN_MB, "f", 1))
    return KILOBYTES.format(locale.toString(max(1, round(size / BYTES_IN_KB))))
