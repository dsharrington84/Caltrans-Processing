from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class BackupResult:
    source_path: Path
    backup_path: Path
    size_bytes: int
    table_count: int
    view_count: int
    sha256: str | None


def safe_slug(value: str) -> str:
    cleaned = "".join(
        character.lower()
        if character.isalnum()
        else "_"
        for character in value.strip()
    )

    return "_".join(
        part
        for part in cleaned.split("_")
        if part
    ) or "manual"


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def inspect_database(path: Path) -> tuple[int, int]:
    con = duckdb.connect(
        str(path),
        read_only=True,
    )

    try:
        table_count = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            """
        ).fetchone()[0]

        view_count = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.views
            """
        ).fetchone()[0]

        return table_count, view_count

    finally:
        con.close()


def create_database_backup(
    database_path: Path,
    backup_directory: Path,
    reason: str,
    verify_checksum: bool = False,
) -> BackupResult:
    database_path = database_path.resolve()
    backup_directory = backup_directory.resolve()

    if not database_path.exists():
        raise FileNotFoundError(
            f"Database not found: {database_path}"
        )

    if database_path.stat().st_size == 0:
        raise RuntimeError(
            f"Database is zero bytes: {database_path}"
        )

    source_tables, source_views = inspect_database(
        database_path
    )

    backup_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    destination = (
        backup_directory
        / (
            "caltrans_pricing_"
            f"{safe_slug(reason)}_"
            f"{timestamp}.duckdb"
        )
    )

    if destination.exists():
        raise FileExistsError(
            f"Backup already exists: {destination}"
        )

    shutil.copy2(
        database_path,
        destination,
    )

    source_size = database_path.stat().st_size
    backup_size = destination.stat().st_size

    if source_size != backup_size:
        destination.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            "Backup size does not match source database."
        )

    backup_tables, backup_views = inspect_database(
        destination
    )

    if (
        source_tables != backup_tables
        or source_views != backup_views
    ):
        destination.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            "Backup object counts do not match source database."
        )

    backup_checksum: str | None = None

    if verify_checksum:
        source_checksum = calculate_sha256(
            database_path
        )

        backup_checksum = calculate_sha256(
            destination
        )

        if source_checksum != backup_checksum:
            destination.unlink(
                missing_ok=True
            )

            raise RuntimeError(
                "Backup checksum does not match source database."
            )

    return BackupResult(
        source_path=database_path,
        backup_path=destination,
        size_bytes=backup_size,
        table_count=backup_tables,
        view_count=backup_views,
        sha256=backup_checksum,
    )


def format_backup_result(
    result: BackupResult,
) -> str:
    lines = [
        f"Backup: {result.backup_path}",
        f"Backup size: {result.size_bytes:,} bytes",
        f"Tables: {result.table_count:,}",
        f"Views: {result.view_count:,}",
    ]

    if result.sha256:
        lines.append(
            f"SHA256: {result.sha256}"
        )

    return "\n".join(lines)
