from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

import duckdb


def connect_database(
    database_path: Path,
    *,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    if not database_path.exists():
        raise FileNotFoundError(
            f"Database not found: {database_path}"
        )

    return duckdb.connect(
        str(database_path),
        read_only=read_only,
    )


def list_database_objects(
    connection: duckdb.DuckDBPyConnection,
) -> set[str]:
    frame = connection.execute(
        """
        SELECT table_name AS object_name
        FROM information_schema.tables

        UNION

        SELECT table_name AS object_name
        FROM information_schema.views
        """
    ).fetchdf()

    return set(
        frame["object_name"].tolist()
    )


def object_exists(
    connection: duckdb.DuckDBPyConnection,
    object_name: str,
) -> bool:
    return (
        object_name
        in list_database_objects(connection)
    )


def require_objects(
    connection: duckdb.DuckDBPyConnection,
    object_names: Iterable[str],
) -> None:
    available = list_database_objects(
        connection
    )

    missing = [
        name
        for name in object_names
        if name not in available
    ]

    if missing:
        raise RuntimeError(
            "Required database objects are missing: "
            + ", ".join(missing)
        )


def quote_identifier(
    identifier: str,
) -> str:
    return (
        '"'
        + identifier.replace(
            '"',
            '""',
        )
        + '"'
    )


def table_row_count(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> int:
    table = quote_identifier(
        table_name
    )

    return int(
        connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {table}
            """
        ).fetchone()[0]
    )


def distinct_count(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    column_name: str,
) -> int:
    table = quote_identifier(
        table_name
    )

    column = quote_identifier(
        column_name
    )

    return int(
        connection.execute(
            f"""
            SELECT COUNT(
                DISTINCT {column}
            )
            FROM {table}
            """
        ).fetchone()[0]
    )


def create_backup(
    database_path: Path,
    backup_directory: Path,
    reason: str,
) -> Path:
    if not database_path.exists():
        raise FileNotFoundError(
            f"Database not found: {database_path}"
        )

    backup_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_reason = re.sub(
        r"[^a-z0-9]+",
        "_",
        reason.lower(),
    ).strip("_")

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_path = (
        backup_directory
        / (
            "caltrans_pricing_before_"
            f"{safe_reason}_"
            f"{timestamp}.duckdb"
        )
    )

    shutil.copy2(
        database_path,
        backup_path,
    )

    source_size = (
        database_path.stat().st_size
    )

    backup_size = (
        backup_path.stat().st_size
    )

    if backup_size != source_size:
        backup_path.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            "Backup validation failed: "
            "file sizes do not match."
        )

    return backup_path


def next_versioned_name(
    connection: duckdb.DuckDBPyConnection,
    prefix: str,
) -> str:
    pattern = re.compile(
        rf"^{re.escape(prefix)}_v(\d+)$"
    )

    versions: list[int] = []

    for object_name in list_database_objects(
        connection
    ):
        match = pattern.match(
            object_name
        )

        if match:
            versions.append(
                int(match.group(1))
            )

    next_version = (
        max(versions) + 1
        if versions
        else 1
    )

    return (
        f"{prefix}_v{next_version}"
    )


def ensure_target_objects_absent(
    connection: duckdb.DuckDBPyConnection,
    object_names: Iterable[str],
) -> None:
    available = list_database_objects(
        connection
    )

    existing = [
        name
        for name in object_names
        if name in available
    ]

    if existing:
        raise RuntimeError(
            "Target database objects already exist: "
            + ", ".join(existing)
        )


def reconcile_contract_sets(
    connection: duckdb.DuckDBPyConnection,
    left_table: str,
    right_table: str,
    *,
    contract_column: str = "contract_number",
) -> int:
    left = quote_identifier(
        left_table
    )

    right = quote_identifier(
        right_table
    )

    column = quote_identifier(
        contract_column
    )

    return int(
        connection.execute(
            f"""
            SELECT COUNT(*)

            FROM (
                SELECT DISTINCT
                    {column} AS contract_number
                FROM {left}
            ) l

            FULL OUTER JOIN (
                SELECT DISTINCT
                    {column} AS contract_number
                FROM {right}
            ) r
                ON r.contract_number
                    = l.contract_number

            WHERE l.contract_number IS NULL
               OR r.contract_number IS NULL
            """
        ).fetchone()[0]
    )
