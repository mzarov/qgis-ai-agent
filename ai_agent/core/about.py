"""What the settings window says about the plugin and the QGIS it runs in."""

import configparser
import os

from qgis.core import Qgis

METADATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metadata.txt")


def plugin_version() -> str:
    """The version in metadata.txt; empty when the file cannot be read."""
    parser = configparser.ConfigParser()
    try:
        parser.read(METADATA, encoding="utf-8")
    except (OSError, configparser.Error):
        return ""
    return parser.get("general", "version", fallback="").strip()


def qgis_version() -> str:
    """Major and minor of the running QGIS, such as 4.2."""
    version = str(getattr(Qgis, "QGIS_VERSION", "") or "")
    return ".".join(version.split("-")[0].split(".")[:2])
