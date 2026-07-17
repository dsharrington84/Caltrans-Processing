from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="verify",
        module="scripts.subcontractor.verify_framework",
        description=(
            "Verify framework modules, directories, "
            "compilation, and database objects."
        ),
        category="Framework",
    ),
    Command(
        name="status",
        module="scripts.subcontractor.run_pipeline",
        description=(
            "Show configured pipeline and database status."
        ),
        category="Framework",
        arguments=("--stage", "status"),
    ),
)
