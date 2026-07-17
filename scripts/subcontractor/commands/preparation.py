from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="cache-stage1",
        module="scripts.subcontractor.run_pipeline",
        description=(
            "Populate the Stage 1 PDF text cache."
        ),
        category="Caching",
        arguments=("--stage", "cache-stage1"),
        aliases=("cache",),
    ),
    Command(
        name="validate-stage1",
        module="scripts.subcontractor.stages.validate_stage1",
        description=(
            "Validate the Stage 1 subcontractor output."
        ),
        category="Validation",
        aliases=("validate",),
    ),
)
