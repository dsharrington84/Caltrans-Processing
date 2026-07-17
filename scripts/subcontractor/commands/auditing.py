from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="audit-bidders",
        module=(
            "scripts.subcontractor.stages."
            "audit_bidder_context"
        ),
        description=(
            "Audit bidder context and identity evidence."
        ),
        category="Auditing",
    ),
    Command(
        name="audit-quarantine",
        module=(
            "scripts.subcontractor.stages."
            "audit_quarantined_contracts"
        ),
        description=(
            "Audit quarantined bidder-block "
            "count mismatches."
        ),
        category="Auditing",
        aliases=("quarantine",),
    ),
    Command(
        name="audit-context",
        module=(
            "scripts.subcontractor.stages."
            "audit_quarantine_context"
        ),
        description=(
            "Extract full-PDF context for "
            "quarantined contracts."
        ),
        category="Auditing",
    ),
)
