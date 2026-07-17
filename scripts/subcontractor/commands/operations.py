from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="doctor",
        module="scripts.subcontractor.doctor",
        description=(
            "Check framework and repository health."
        ),
        category="Operations",
    ),
    Command(
        name="stats",
        module="scripts.subcontractor.operations",
        description=(
            "Show production and pipeline statistics."
        ),
        category="Operations",
        arguments=("stats",),
    ),
    Command(
        name="config-show",
        module="scripts.subcontractor.operations",
        description=(
            "Display subcontractor configuration "
            "and resolved paths."
        ),
        category="Operations",
        arguments=("config-show",),
        aliases=("config",),
    ),
    Command(
        name="backup",
        module="scripts.subcontractor.maintenance",
        description=(
            "Create and validate a database backup."
        ),
        category="Operations",
        arguments=("backup",),
    ),
    Command(
        name="logs",
        module="scripts.subcontractor.maintenance",
        description=(
            "List recent logs, reports, and backups."
        ),
        category="Operations",
        arguments=("logs",),
    ),
    Command(
        name="report",
        module="scripts.subcontractor.maintenance",
        description=(
            "Show a consolidated pipeline report."
        ),
        category="Operations",
        arguments=("report",),
    ),
)
