from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="run-alt",
        module=(
            "scripts.subcontractor.stages."
            "run_alternate_pipeline"
        ),
        description=(
            "Run the complete alternate-layout pipeline."
        ),
        category="Pipelines",
        aliases=("pipeline-alt",),
    ),
)
