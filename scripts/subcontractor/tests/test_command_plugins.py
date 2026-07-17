from __future__ import annotations

from collections import Counter

from scripts.subcontractor.commands import (
    discover_commands,
)


def main() -> int:
    commands = discover_commands()

    names = [
        command.name
        for command in commands
    ]

    required = {
        "verify",
        "status",
        "cache-stage1",
        "validate-stage1",
        "parse-alt-pages",
        "group-alt",
        "reconcile-alt",
        "parse-alt",
        "certify-alt",
        "identity-alt",
        "promote-alt",
        "audit-bidders",
        "audit-quarantine",
        "audit-context",
        "run-alt",
        "doctor",
        "stats",
        "config-show",
        "backup",
        "logs",
        "report",
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

    duplicate_names = [
        name
        for name, count in Counter(
            names
        ).items()
        if count > 1
    ]

    if duplicate_names:
        raise RuntimeError(
            "Duplicate plugin command names: "
            + ", ".join(
                sorted(duplicate_names)
            )
        )

    aliases = [
        alias
        for command in commands
        for alias in command.aliases
    ]

    required_aliases = {
        "cache",
        "validate",
        "detect-alt",
        "quarantine",
        "pipeline-alt",
        "config",
        "preflight",
    }

    missing_aliases = (
        required_aliases.difference(
            aliases
        )
    )

    if missing_aliases:
        raise RuntimeError(
            "Missing plugin aliases: "
            + ", ".join(
                sorted(missing_aliases)
            )
        )

    duplicate_aliases = [
        alias
        for alias, count in Counter(
            aliases
        ).items()
        if count > 1
    ]

    if duplicate_aliases:
        raise RuntimeError(
            "Duplicate plugin aliases: "
            + ", ".join(
                sorted(duplicate_aliases)
            )
        )

    print()
    print("COMMAND PLUGIN TEST PASSED")
    print(
        "Commands: "
        + ", ".join(sorted(names))
    )
    print(
        "Aliases: "
        + ", ".join(sorted(aliases))
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
