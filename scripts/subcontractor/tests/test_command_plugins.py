from __future__ import annotations

from scripts.subcontractor.commands import (
    discover_commands,
)


def main() -> int:
    commands = discover_commands()

    names = {
        command.name
        for command in commands
    }

    required = {
        "test",
        "check",
    }

    missing = required.difference(
        names
    )

    if missing:
        raise RuntimeError(
            "Missing plugin commands: "
            + ", ".join(sorted(missing))
        )

    aliases = {
        alias
        for command in commands
        for alias in command.aliases
    }

    if "preflight" not in aliases:
        raise RuntimeError(
            "Missing preflight alias."
        )

    print()
    print("COMMAND PLUGIN TEST PASSED")
    print(
        "Commands: "
        + ", ".join(sorted(names))
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
