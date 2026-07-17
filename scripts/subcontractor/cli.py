from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from scripts.subcontractor.command_model import (
    Command,
)
from scripts.subcontractor.commands import (
    discover_commands,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


ALL_COMMANDS: tuple[Command, ...] = (
    discover_commands()
)


def build_command_index() -> dict[str, Command]:
    index: dict[str, Command] = {}

    for command in ALL_COMMANDS:
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

    for command in ALL_COMMANDS:
        if command.category not in categories:
            categories.append(
                command.category
            )

    for category in categories:
        print()
        print(category.upper())
        print("-" * 100)

        for command in ALL_COMMANDS:
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
    for command in ALL_COMMANDS:
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
