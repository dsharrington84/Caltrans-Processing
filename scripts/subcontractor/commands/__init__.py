from __future__ import annotations

import importlib
import pkgutil

from scripts.subcontractor.command_model import (
    Command,
)


def discover_commands() -> tuple[Command, ...]:
    commands: list[Command] = []

    package_prefix = __name__ + "."

    for module_info in pkgutil.iter_modules(
        __path__,
        package_prefix,
    ):
        if module_info.name.endswith(
            ".__init__"
        ):
            continue

        module = importlib.import_module(
            module_info.name
        )

        exported = getattr(
            module,
            "COMMANDS",
            (),
        )

        if not isinstance(
            exported,
            tuple,
        ):
            raise TypeError(
                f"{module_info.name}.COMMANDS "
                "must be a tuple."
            )

        for command in exported:
            if not isinstance(
                command,
                Command,
            ):
                raise TypeError(
                    f"{module_info.name} exported "
                    "a non-Command value."
                )

            commands.append(
                command
            )

    return tuple(commands)
