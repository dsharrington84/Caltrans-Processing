from __future__ import annotations

from scripts.subcontractor.command_model import (
    Command,
)


COMMANDS: tuple[Command, ...] = (
    Command(
        name="parse-alt-pages",
        module=(
            "scripts.subcontractor.stages."
            "parse_alternate_layout"
        ),
        description=(
            "Detect alternate-layout subcontractor pages."
        ),
        category="Alternate Parsing",
        aliases=("detect-alt",),
    ),
    Command(
        name="group-alt",
        module=(
            "scripts.subcontractor.stages."
            "group_alternate_layout"
        ),
        description=(
            "Group alternate-layout pages into bidder blocks."
        ),
        category="Alternate Parsing",
    ),
    Command(
        name="reconcile-alt",
        module=(
            "scripts.subcontractor.stages."
            "reconcile_alternate_blocks"
        ),
        description=(
            "Reconcile alternate bidder blocks "
            "with ranked bidders."
        ),
        category="Alternate Parsing",
    ),
    Command(
        name="parse-alt",
        module=(
            "scripts.subcontractor.stages."
            "stage2_alternate_parser"
        ),
        description=(
            "Parse alternate-layout disclosure rows."
        ),
        category="Alternate Parsing",
    ),
)
