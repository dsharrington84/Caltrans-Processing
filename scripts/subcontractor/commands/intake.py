from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="intake-folder",
        module=(
            "scripts.subcontractor.intake_folder"
        ),
        description=(
            "Inventory a PDF folder and classify "
            "contracts against the processing pipeline."
        ),
        category="Intake",
        aliases=(
            "folder-intake",
            "intake",
        ),
    ),
)
