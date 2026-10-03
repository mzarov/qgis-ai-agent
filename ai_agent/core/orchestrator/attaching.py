"""The orchestrator's half of attachments: what the chat shows and what the model receives."""

import os
from dataclasses import dataclass, field

from ai_agent.core.agent.request import detect_images_unsupported
from ai_agent.core.attachments import attach, encode_picture
from ai_agent.core.orchestrator.contracts import DockWidgetContract
from ai_agent.i18n import tr

NOT_ATTACHED = tr("Could not attach {0}: {1}")
ATTACHED = tr("Attached: {0}")
NO_EYES = tr("This model does not accept pictures, so {0} was not sent.")
NAME_SEPARATOR = ", "


@dataclass
class Pictures:
    encoded: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)


def files_attached(dock: DockWidgetContract, paths: list[str]) -> None:
    """Data files become layers mentioned in the request; pictures wait in the composer."""
    outcome = attach(paths)
    if outcome.added:
        dock.mention_layers(outcome.added)
    for path in outcome.images:
        dock.add_attachment(path)
    for path, reason in outcome.failed:
        dock.add_system_message(NOT_ATTACHED.format(os.path.basename(path), reason))


def take_pictures(dock: DockWidgetContract) -> Pictures:
    """The composer's pictures, encoded for the request; a model known to be blind gets none."""
    pictures = Pictures()
    paths = dock.take_attachments()
    if not paths:
        return pictures
    names = [os.path.basename(path) for path in paths]
    if detect_images_unsupported():
        dock.add_system_message(NO_EYES.format(NAME_SEPARATOR.join(names)))
        return pictures
    for path, name in zip(paths, names, strict=True):
        try:
            pictures.encoded.append(encode_picture(path))
        except ValueError as error:
            dock.add_system_message(NOT_ATTACHED.format(name, error))
            continue
        pictures.names.append(name)
    return pictures


def with_names(text: str, pictures: Pictures) -> str:
    """The request as the chat and the history keep it: the pictures named on a line of their own."""
    if not pictures.names:
        return text
    return f"{text}\n{ATTACHED.format(NAME_SEPARATOR.join(pictures.names))}"
