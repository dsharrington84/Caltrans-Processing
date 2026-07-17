from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    module: str
    description: str
    category: str
    arguments: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
