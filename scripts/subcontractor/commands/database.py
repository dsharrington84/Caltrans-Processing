from __future__ import annotations

from scripts.subcontractor.command_model import Command


COMMANDS = (
    Command(
        name="doctor-db",
        module="scripts.subcontractor.database_doctor",
        description=(
            "Run read-only database health checks."
        ),
        category="Database",
        aliases=(
            "db-doctor",
        ),
    ),
)
