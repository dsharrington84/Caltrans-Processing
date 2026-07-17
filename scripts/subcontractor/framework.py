from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from scripts.subcontractor.backup_service import (
    BackupResult,
    create_database_backup,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT
    / "config/subcontractor/settings.json"
)

DEFAULT_DATABASE_PATH = (
    PROJECT_ROOT
    / "data/database/caltrans_pricing.duckdb"
)

DEFAULT_BACKUP_DIRECTORY = (
    PROJECT_ROOT
    / "data/database/backups"
)

DEFAULT_CACHE_DIRECTORY = (
    PROJECT_ROOT
    / "data/cache/subcontractor_pdf_text"
)

DEFAULT_LOG_DIRECTORY = (
    PROJECT_ROOT
    / "data/logs/subcontractor"
)

DEFAULT_REPORT_DIRECTORY = (
    PROJECT_ROOT
    / "data/reports/subcontractor"
)


@dataclass(frozen=True)
class FrameworkPaths:
    project_root: Path
    config: Path
    database: Path
    backups: Path
    cache: Path
    logs: Path
    reports: Path


@dataclass(frozen=True)
class FrameworkContext:
    settings: dict[str, Any]
    paths: FrameworkPaths
    target_year: int | None
    target_districts: tuple[int, ...]
    tables: dict[str, str]

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
    ) -> "FrameworkContext":
        selected_config = (
            config_path or DEFAULT_CONFIG_PATH
        ).resolve()

        settings = load_settings(
            selected_config
        )

        paths = FrameworkPaths(
            project_root=PROJECT_ROOT,
            config=selected_config,
            database=resolve_configured_path(
                settings.get("database_path"),
                DEFAULT_DATABASE_PATH,
            ),
            backups=resolve_configured_path(
                settings.get("backup_directory"),
                DEFAULT_BACKUP_DIRECTORY,
            ),
            cache=resolve_configured_path(
                settings.get("cache_directory"),
                DEFAULT_CACHE_DIRECTORY,
            ),
            logs=resolve_configured_path(
                settings.get("log_directory"),
                DEFAULT_LOG_DIRECTORY,
            ),
            reports=resolve_configured_path(
                settings.get("report_directory"),
                DEFAULT_REPORT_DIRECTORY,
            ),
        )

        raw_year = settings.get(
            "target_year"
        )

        target_year = (
            int(raw_year)
            if raw_year is not None
            else None
        )

        target_districts = tuple(
            int(value)
            for value in settings.get(
                "target_districts",
                [],
            )
        )

        tables = {
            str(key): str(value)
            for key, value in settings.get(
                "tables",
                {},
            ).items()
        }

        return cls(
            settings=settings,
            paths=paths,
            target_year=target_year,
            target_districts=target_districts,
            tables=tables,
        )

    def connect(
        self,
        *,
        read_only: bool = False,
    ) -> duckdb.DuckDBPyConnection:
        if not self.paths.database.exists():
            raise FileNotFoundError(
                "Database not found: "
                f"{self.paths.database}"
            )

        return duckdb.connect(
            str(self.paths.database),
            read_only=read_only,
        )

    def table_exists(
        self,
        table_name: str,
        *,
        connection: duckdb.DuckDBPyConnection
        | None = None,
    ) -> bool:
        owns_connection = (
            connection is None
        )

        con = (
            connection
            if connection is not None
            else self.connect(
                read_only=True
            )
        )

        try:
            return bool(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name = ?
                    """,
                    [table_name],
                ).fetchone()[0]
            )

        finally:
            if owns_connection:
                con.close()

    def create_backup(
        self,
        reason: str,
        *,
        verify_checksum: bool = False,
    ) -> BackupResult:
        return create_database_backup(
            database_path=self.paths.database,
            backup_directory=self.paths.backups,
            reason=reason,
            verify_checksum=verify_checksum,
        )


def load_settings(
    config_path: Path,
) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration not found: {config_path}"
        )

    with config_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        settings = json.load(file)

    if not isinstance(
        settings,
        dict,
    ):
        raise TypeError(
            "Configuration root must be a JSON object."
        )

    return settings


def resolve_configured_path(
    value: Any,
    default: Path,
) -> Path:
    if value in {
        None,
        "",
    }:
        return default.resolve()

    path = Path(
        str(value)
    ).expanduser()

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()
