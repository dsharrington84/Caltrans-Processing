from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="test",
        module="scripts.subcontractor.quality",
        description=(
            "Run all subcontractor test modules."
        ),
        category="Quality",
        arguments=("test",),
    ),
    Command(
        name="check",
        module="scripts.subcontractor.quality",
        description=(
            "Run verification, doctor, and all tests."
        ),
        category="Quality",
        arguments=("check",),
        aliases=("preflight",),
    ),
)
