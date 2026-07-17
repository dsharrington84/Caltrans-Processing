from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb

from scripts.subcontractor.backup_service import (
    create_database_backup,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        database = root / "test.duckdb"
        backups = root / "backups"

        con = duckdb.connect(
            str(database)
        )

        try:
            con.execute(
                """
                CREATE TABLE test_table (
                    id INTEGER,
                    value VARCHAR
                )
                """
            )

            con.execute(
                """
                INSERT INTO test_table
                VALUES
                    (1, 'alpha'),
                    (2, 'beta')
                """
            )

        finally:
            con.close()

        result = create_database_backup(
            database_path=database,
            backup_directory=backups,
            reason="unit_test",
            verify_checksum=True,
        )

        if not result.backup_path.exists():
            raise RuntimeError(
                "Backup was not created."
            )

        if result.size_bytes <= 0:
            raise RuntimeError(
                "Backup is empty."
            )

        backup_con = duckdb.connect(
            str(result.backup_path),
            read_only=True,
        )

        try:
            row_count = backup_con.execute(
                """
                SELECT COUNT(*)
                FROM test_table
                """
            ).fetchone()[0]

        finally:
            backup_con.close()

        if row_count != 2:
            raise RuntimeError(
                f"Expected 2 rows, found {row_count}."
            )

        print()
        print("BACKUP SERVICE TEST PASSED")
        print(f"Backup: {result.backup_path}")
        print(f"Rows verified: {row_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
