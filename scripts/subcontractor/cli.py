from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Command:
    name: str
    module: str
    description: str
    arguments: tuple[str, ...] = ()


COMMANDS: tuple[Command, ...] = (
    Command(
        name="verify",
        module="scripts.subcontractor.verify_framework",
        description="Verify framework modules, directories, and database objects.",
    ),
    Command(
        name="status",
        module="scripts.subcontractor.run_pipeline",
        description="Show configured pipeline and database status.",
        arguments=("--stage", "status"),
    ),
    Command(
        name="cache-stage1",
        module="scripts.subcontractor.run_pipeline",
        description="Populate the Stage 1 PDF text cache.",
        arguments=("--stage", "cache-stage1"),
    ),
    Command(
        name="validate-stage1",
        module="scripts.subcontractor.stages.validate_stage1",
        description="Validate the Stage 1 subcontractor output.",
    ),
    Command(
        name="parse-alt-pages",
        module="scripts.subcontractor.stages.parse_alternate_layout",
        description="Detect alternate-layout subcontractor pages.",
    ),
    Command(
        name="group-alt",
        module="scripts.subcontractor.stages.group_alternate_layout",
        description="Group alternate-layout pages into bidder blocks.",
    ),
    Command(
        name="reconcile-alt",
        module="scripts.subcontractor.stages.reconcile_alternate_blocks",
        description="Reconcile alternate bidder blocks with ranked bidders.",
    ),
    Command(
        name="parse-alt",
        module="scripts.subcontractor.stages.stage2_alternate_parser",
        description="Parse alternate-layout disclosure rows.",
    ),
    Command(
        name="certify-alt",
        module="scripts.subcontractor.stages.certify_alternate_stage2",
        description="Certify alternate-layout disclosure rows.",
    ),
    Command(
        name="identity-alt",
        module="scripts.subcontractor.stages.build_identity_overlay",
        description="Build the alternate prime-bidder identity overlay.",
    ),
    Command(
        name="promote-alt",
        module="scripts.subcontractor.stages.promote_alternate_disclosures",
        description="Promote certified alternate-layout disclosures.",
    ),
    Command(
        name="audit-bidders",
        module="scripts.subcontractor.stages.audit_bidder_context",
        description="Audit bidder context and identity evidence.",
    ),
    Command(
        name="audit-quarantine",
        module="scripts.subcontractor.stages.audit_quarantined_contracts",
        description="Audit quarantined bidder-block count mismatches.",
    ),
    Command(
        name="audit-context",
        module="scripts.subcontractor.stages.audit_quarantine_context",
        description="Extract full-PDF context for quarantined contracts.",
    ),
)


COMMAND_INDEX = {
    command.name: command
    for command in COMMANDS
}


def print_command_list() -> None:
    print()
    print("SUBCONTRACTOR COMMAND LIBRARY")
    print("=" * 100)

    for command in COMMANDS:
        print(
            f"{command.name:<22} "
            f"{command.description}"
        )

    print()


def run_module(
    module: str,
    arguments: Sequence[str],
) -> int:
    command = [
        sys.executable,
        "-m",
        module,
        *arguments,
    ]

    print()
    print("RUNNING")
    print("-" * 100)
    print(" ".join(command))
    print()

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )

    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subcontractor",
        description=(
            "Command library for the Caltrans "
            "subcontractor-processing framework."
        ),
    )

    parser.add_argument(
        "command",
        nargs="?",
        help="Command to run. Use 'list' to show available commands.",
    )

    parser.add_argument(
        "extra_arguments",
        nargs=argparse.REMAINDER,
        help="Additional arguments passed to the selected module.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.command in {
        None,
        "list",
        "help",
        "--help",
        "-h",
    }:
        print_command_list()
        return 0

    command = COMMAND_INDEX.get(
        arguments.command
    )

    if command is None:
        print(
            f"Unknown command: {arguments.command}",
            file=sys.stderr,
        )
        print_command_list()
        return 2

    module_arguments = [
        *command.arguments,
        *arguments.extra_arguments,
    ]

    return run_module(
        command.module,
        module_arguments,
    )


if __name__ == "__main__":
    raise SystemExit(main())
