from __future__ import annotations

import json
import tempfile
from pathlib import Path

import duckdb

from scripts.subcontractor.framework import (
    FrameworkContext,
)
from scripts.subcontractor.stage_runtime import (
    Stage,
)


class ReadOnlyTestStage(Stage):
    name = "read-only-test-stage"
    description = "Validate the read-only stage lifecycle."

    def execute(self) -> dict[str, int]:
        if self.connection is None:
            raise RuntimeError(
                "Database connection was not opened."
            )

        row_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM test_table
            """
        ).fetchone()[0]

        return {
            "row_count": row_count,
        }

    def validate_result(
        self,
        details: dict[str, int],
    ) -> None:
        if details["row_count"] != 2:
            raise RuntimeError(
                "Unexpected read-only row count."
            )


class WritingTestStage(Stage):
    name = "writing-test-stage"
    description = "Validate backup and write lifecycle."
    writes_database = True
    backup_reason = "stage_runtime_test"

    def execute(self) -> dict[str, int]:
        if self.connection is None:
            raise RuntimeError(
                "Database connection was not opened."
            )

        self.connection.execute(
            """
            INSERT INTO test_table
            VALUES (3, 'gamma')
            """
        )

        row_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM test_table
            """
        ).fetchone()[0]

        return {
            "row_count": row_count,
        }

    def validate_result(
        self,
        details: dict[str, int],
    ) -> None:
        if details["row_count"] != 3:
            raise RuntimeError(
                "Database write was not validated."
            )


def build_test_context(
    root: Path,
) -> FrameworkContext:
    database = root / "test.duckdb"
    backups = root / "backups"
    cache = root / "cache"
    logs = root / "logs"
    reports = root / "reports"

    for directory in (
        backups,
        cache,
        logs,
        reports,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

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

    config = root / "settings.json"

    config.write_text(
        json.dumps(
            {
                "database_path": str(database),
                "backup_directory": str(backups),
                "cache_directory": str(cache),
                "log_directory": str(logs),
                "report_directory": str(reports),
                "target_year": 2025,
                "target_districts": [
                    7,
                    8,
                    11,
                    12,
                ],
                "tables": {},
            }
        ),
        encoding="utf-8",
    )

    return FrameworkContext.load(
        config_path=config
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        context = build_test_context(
            root
        )

        read_result = ReadOnlyTestStage(
            context
        ).run()

        if read_result.status != "PASSED":
            raise RuntimeError(
                "Read-only stage failed."
            )

        write_result = WritingTestStage(
            context
        ).run()

        if write_result.status != "PASSED":
            raise RuntimeError(
                "Writing stage failed."
            )

        backup_files = list(
            context.paths.backups.glob(
                "*.duckdb"
            )
        )

        if len(backup_files) != 1:
            raise RuntimeError(
                "Expected exactly one stage backup; "
                f"found {len(backup_files)}."
            )

        con = context.connect(
            read_only=True
        )

        try:
            final_count = con.execute(
                """
                SELECT COUNT(*)
                FROM test_table
                """
            ).fetchone()[0]

        finally:
            con.close()

        if final_count != 3:
            raise RuntimeError(
                "Writing stage result was not persisted."
            )

        print()
        print("STAGE RUNTIME TEST PASSED")
        print(f"Backup: {backup_files[0]}")
        print(f"Final rows: {final_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
