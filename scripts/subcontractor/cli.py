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
    category: str
    arguments: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


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


def build_command_index() -> dict[str, Command]:
    index: dict[str, Command] = {}

    for command in COMMANDS:
        names = (
            command.name,
            *command.aliases,
        )

        for name in names:
            if name in index:
                raise RuntimeError(
                    f"Duplicate command or alias: {name}"
                )

            index[name] = command

    return index


COMMAND_INDEX = build_command_index()


def print_header() -> None:
    print()
    print("CALTRANS SUBCONTRACTOR PROCESSING")
    print("=" * 100)


def print_command_list() -> None:
    print_header()

    categories: list[str] = []

    for command in COMMANDS:
        if command.category not in categories:
            categories.append(
                command.category
            )

    for category in categories:
        print()
        print(category.upper())
        print("-" * 100)

        for command in COMMANDS:
            if command.category != category:
                continue

            alias_text = ""

            if command.aliases:
                alias_text = (
                    " "
                    + "[aliases: "
                    + ", ".join(command.aliases)
                    + "]"
                )

            print(
                f"{command.name:<22} "
                f"{command.description}"
                f"{alias_text}"
            )

    print()
    print("USAGE")
    print("-" * 100)
    print(
        "subcontractor <command> "
        "[command arguments]"
    )
    print(
        "subcontractor describe <command>"
    )
    print(
        "subcontractor commands"
    )
    print()


def print_command_names() -> None:
    for command in COMMANDS:
        print(command.name)


def describe_command(
    requested_name: str,
) -> int:
    command = COMMAND_INDEX.get(
        requested_name
    )

    if command is None:
        print(
            f"Unknown command: {requested_name}",
            file=sys.stderr,
        )
        return 2

    print_header()
    print()
    print(command.name.upper())
    print("-" * 100)
    print(f"Category: {command.category}")
    print(f"Description: {command.description}")
    print(f"Module: {command.module}")

    if command.arguments:
        print(
            "Default arguments: "
            + " ".join(command.arguments)
        )
    else:
        print("Default arguments: none")

    if command.aliases:
        print(
            "Aliases: "
            + ", ".join(command.aliases)
        )
    else:
        print("Aliases: none")

    print()
    print("COMMAND")
    print("-" * 100)
    print(
        f"subcontractor {command.name}"
    )
    print()

    return 0


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
        add_help=True,
        description=(
            "Command library for the Caltrans "
            "subcontractor-processing framework."
        ),
    )

    parser.add_argument(
        "command",
        nargs="?",
        help=(
            "Command to run. Use 'help' or "
            "'list' to show available commands."
        ),
    )

    parser.add_argument(
        "extra_arguments",
        nargs=argparse.REMAINDER,
        help=(
            "Additional arguments passed "
            "to the selected command."
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.command in {
        None,
        "list",
        "help",
    }:
        print_command_list()
        return 0

    if arguments.command == "commands":
        print_command_names()
        return 0

    if arguments.command == "describe":
        if not arguments.extra_arguments:
            print(
                "Usage: subcontractor "
                "describe <command>",
                file=sys.stderr,
            )
            return 2

        return describe_command(
            arguments.extra_arguments[0]
        )

    command = COMMAND_INDEX.get(
        arguments.command
    )

    if command is None:
        print(
            f"Unknown command: {arguments.command}",
            file=sys.stderr,
        )
        print(
            "Run 'subcontractor help' "
            "to view available commands.",
            file=sys.stderr,
        )
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
