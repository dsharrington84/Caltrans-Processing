from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="certify-alt",
        module=(
            "scripts.subcontractor.stages."
            "certify_alternate_stage2"
        ),
        description=(
            "Certify alternate-layout disclosure rows."
        ),
        category="Certification",
    ),
    Command(
        name="identity-alt",
        module=(
            "scripts.subcontractor.stages."
            "build_identity_overlay"
        ),
        description=(
            "Build the alternate prime-bidder "
            "identity overlay."
        ),
        category="Certification",
    ),
    Command(
        name="promote-alt",
        module=(
            "scripts.subcontractor.stages."
            "promote_alternate_disclosures"
        ),
        description=(
            "Promote certified alternate-layout disclosures."
        ),
        category="Promotion",
    ),
)
