import base64
from typing import Any

from qgis.PyQt.QtCore import QBuffer, QIODevice

IMAGE_FORMAT = "PNG"
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def encoded_png(image: Any) -> str:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, IMAGE_FORMAT):
        raise ValueError("QGIS could not encode the rendered picture into an image.")
    data = bytes(buffer.data())
    buffer.close()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"The rendered image is {len(data) // 1024 // 1024} MB, over the limit of "
            f"{MAX_IMAGE_BYTES // 1024 // 1024} MB. Ask for a smaller width."
        )
    return base64.b64encode(data).decode("ascii")
