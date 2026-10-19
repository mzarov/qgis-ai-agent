import configparser
import os

from qgis.core import Qgis

METADATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metadata.txt")


def plugin_version() -> str:
    parser = configparser.ConfigParser()
    try:
        parser.read(METADATA, encoding="utf-8")
    except (OSError, configparser.Error):
        return ""
    return parser.get("general", "version", fallback="").strip()


def qgis_version() -> str:
    version = str(getattr(Qgis, "QGIS_VERSION", "") or "")
    return ".".join(version.split("-")[0].split(".")[:2])
