from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SETTINGS_PATH = (
    PROJECT_ROOT
    / "config"
    / "subcontractor"
    / "settings.json"
)


@dataclass(frozen=True)
class PipelineConfig:
    project_root: Path
    database_path: Path
    backup_directory: Path
    cache_directory: Path
    log_directory: Path
    target_year: int
    target_districts: tuple[int, ...]
    tables: dict[str, str]

    @classmethod
    def load(
        cls,
        settings_path: Path | None = None,
    ) -> "PipelineConfig":
        path = settings_path or DEFAULT_SETTINGS_PATH

        if not path.exists():
            raise FileNotFoundError(
                f"Settings file not found: {path}"
            )

        settings: dict[str, Any] = json.loads(
            path.read_text(encoding="utf-8")
        )

        return cls(
            project_root=PROJECT_ROOT,
            database_path=(
                PROJECT_ROOT
                / settings["database_path"]
            ),
            backup_directory=(
                PROJECT_ROOT
                / settings["backup_directory"]
            ),
            cache_directory=(
                PROJECT_ROOT
                / settings["cache_directory"]
            ),
            log_directory=(
                PROJECT_ROOT
                / settings["log_directory"]
            ),
            target_year=int(
                settings["target_year"]
            ),
            target_districts=tuple(
                int(value)
                for value in settings["target_districts"]
            ),
            tables=dict(
                settings["tables"]
            ),
        )

    def ensure_directories(self) -> None:
        for directory in (
            self.backup_directory,
            self.cache_directory,
            self.log_directory,
        ):
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )
