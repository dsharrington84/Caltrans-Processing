from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

import duckdb

from scripts.subcontractor.framework import FrameworkContext


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class DatabaseCheck:
    name: str
    status: CheckStatus
    summary: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatabaseDoctorReport:
    database_path: str
    checks: tuple[DatabaseCheck, ...]

    @property
    def passed(self) -> int:
        return sum(
            check.status == CheckStatus.PASS
            for check in self.checks
        )

    @property
    def warnings(self) -> int:
        return sum(
            check.status == CheckStatus.WARN
            for check in self.checks
        )

    @property
    def failures(self) -> int:
        return sum(
            check.status == CheckStatus.FAIL
            for check in self.checks
        )

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0


REQUIRED_PRODUCTION_OBJECTS = (
    "bid_tab_subcontractor_relationship_current",
    "bid_tab_subcontractor_relationship_current_v2",
    "bid_tab_subcontractor_relationship_normalized_2025_v2",
)


RELATIONSHIP_ID_CANDIDATES = (
    "relationship_id",
    "disclosure_id",
    "subcontractor_disclosure_id",
)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def main_schema_objects(
    con: duckdb.DuckDBPyConnection,
) -> list[tuple[str, str]]:
    rows = con.execute(
        """
        SELECT
            table_name,
            table_type

        FROM information_schema.tables

        WHERE table_schema = 'main'

        ORDER BY
            table_name
        """
    ).fetchall()

    return [
        (
            str(table_name),
            str(table_type),
        )
        for table_name, table_type in rows
    ]


def table_columns(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
) -> tuple[str, ...]:
    rows = con.execute(
        f"DESCRIBE {quote_identifier(table_name)}"
    ).fetchall()

    return tuple(
        str(row[0])
        for row in rows
    )


def check_database_access(
    con: duckdb.DuckDBPyConnection,
) -> DatabaseCheck:
    try:
        value = con.execute(
            "SELECT 1"
        ).fetchone()[0]

        if value != 1:
            return DatabaseCheck(
                name="DATABASE_ACCESS",
                status=CheckStatus.FAIL,
                summary=(
                    "Database connection returned an "
                    "unexpected validation result."
                ),
            )

        return DatabaseCheck(
            name="DATABASE_ACCESS",
            status=CheckStatus.PASS,
            summary="Read-only database connection succeeded.",
        )

    except Exception as error:
        return DatabaseCheck(
            name="DATABASE_ACCESS",
            status=CheckStatus.FAIL,
            summary="Unable to query the database.",
            details=(str(error),),
        )


def check_schema_inventory(
    con: duckdb.DuckDBPyConnection,
) -> DatabaseCheck:
    objects = main_schema_objects(
        con
    )

    base_tables = sum(
        table_type == "BASE TABLE"
        for _, table_type in objects
    )

    views = len(objects) - base_tables

    if not objects:
        return DatabaseCheck(
            name="SCHEMA_INVENTORY",
            status=CheckStatus.FAIL,
            summary="No objects were found in the main schema.",
        )

    return DatabaseCheck(
        name="SCHEMA_INVENTORY",
        status=CheckStatus.PASS,
        summary=(
            f"Found {base_tables:,} base tables "
            f"and {views:,} views."
        ),
    )


def check_empty_tables(
    con: duckdb.DuckDBPyConnection,
) -> DatabaseCheck:
    objects = main_schema_objects(
        con
    )

    empty_tables: list[str] = []
    unreadable_tables: list[str] = []

    for table_name, table_type in objects:
        if table_type != "BASE TABLE":
            continue

        try:
            row_count = con.execute(
                f"""
                SELECT COUNT(*)
                FROM {quote_identifier(table_name)}
                """
            ).fetchone()[0]

            if row_count == 0:
                empty_tables.append(
                    table_name
                )

        except Exception as error:
            unreadable_tables.append(
                f"{table_name}: {error}"
            )

    if unreadable_tables:
        return DatabaseCheck(
            name="EMPTY_TABLES",
            status=CheckStatus.FAIL,
            summary=(
                f"{len(unreadable_tables):,} table(s) "
                "could not be inspected."
            ),
            details=tuple(
                unreadable_tables[:25]
            ),
        )

    if empty_tables:
        return DatabaseCheck(
            name="EMPTY_TABLES",
            status=CheckStatus.WARN,
            summary=(
                f"{len(empty_tables):,} empty base table(s) found."
            ),
            details=tuple(
                empty_tables[:50]
            ),
        )

    return DatabaseCheck(
        name="EMPTY_TABLES",
        status=CheckStatus.PASS,
        summary="No empty base tables found.",
    )


def check_required_production_tables(
    con: duckdb.DuckDBPyConnection,
) -> DatabaseCheck:
    available = {
        table_name
        for table_name, _ in main_schema_objects(
            con
        )
    }

    missing = [
        name
        for name in REQUIRED_PRODUCTION_OBJECTS
        if name not in available
    ]

    if missing:
        return DatabaseCheck(
            name="REQUIRED_PRODUCTION_TABLES",
            status=CheckStatus.FAIL,
            summary=(
                f"{len(missing):,} required production "
                "object(s) are missing."
            ),
            details=tuple(
                missing
            ),
        )

    return DatabaseCheck(
        name="REQUIRED_PRODUCTION_TABLES",
        status=CheckStatus.PASS,
        summary=(
            f"All {len(REQUIRED_PRODUCTION_OBJECTS):,} "
            "required production objects are present."
        ),
    )


def relationship_tables(
    con: duckdb.DuckDBPyConnection,
) -> Iterable[str]:
    for table_name, table_type in main_schema_objects(
        con
    ):
        if (
            table_type == "BASE TABLE"
            and "relationship" in table_name.lower()
        ):
            yield table_name


def check_duplicate_relationship_ids(
    con: duckdb.DuckDBPyConnection,
) -> DatabaseCheck:
    duplicate_findings: list[str] = []
    inspected_tables = 0

    for table_name in relationship_tables(
        con
    ):
        columns = table_columns(
            con,
            table_name,
        )

        identifier = next(
            (
                candidate
                for candidate in RELATIONSHIP_ID_CANDIDATES
                if candidate in columns
            ),
            None,
        )

        if identifier is None:
            continue

        inspected_tables += 1

        duplicate_count = con.execute(
            f"""
            SELECT COUNT(*)

            FROM (
                SELECT
                    {quote_identifier(identifier)}

                FROM {quote_identifier(table_name)}

                WHERE {quote_identifier(identifier)}
                    IS NOT NULL

                GROUP BY
                    {quote_identifier(identifier)}

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]

        if duplicate_count:
            duplicate_findings.append(
                f"{table_name}.{identifier}: "
                f"{duplicate_count:,} duplicated value(s)"
            )

    if duplicate_findings:
        return DatabaseCheck(
            name="DUPLICATE_RELATIONSHIP_IDS",
            status=CheckStatus.FAIL,
            summary=(
                f"Duplicate identifiers were found in "
                f"{len(duplicate_findings):,} table(s)."
            ),
            details=tuple(
                duplicate_findings
            ),
        )

    if inspected_tables == 0:
        return DatabaseCheck(
            name="DUPLICATE_RELATIONSHIP_IDS",
            status=CheckStatus.WARN,
            summary=(
                "No relationship tables containing a recognized "
                "identifier column were found."
            ),
        )

    return DatabaseCheck(
        name="DUPLICATE_RELATIONSHIP_IDS",
        status=CheckStatus.PASS,
        summary=(
            f"No duplicate identifiers found across "
            f"{inspected_tables:,} inspected relationship table(s)."
        ),
    )


def run_database_doctor(
    context: FrameworkContext | None = None,
) -> DatabaseDoctorReport:
    active_context = (
        context
        if context is not None
        else FrameworkContext.load()
    )

    con = active_context.connect(
        read_only=True,
    )

    try:
        checks = (
            check_database_access(
                con
            ),
            check_schema_inventory(
                con
            ),
            check_empty_tables(
                con
            ),
            check_duplicate_relationship_ids(
                con
            ),
            check_required_production_tables(
                con
            ),
        )

    finally:
        con.close()

    return DatabaseDoctorReport(
        database_path=str(
            active_context.paths.database
        ),
        checks=checks,
    )


def print_database_doctor_report(
    report: DatabaseDoctorReport,
) -> None:
    print()
    print("DATABASE DOCTOR")
    print("=" * 120)
    print(f"Database: {report.database_path}")

    for check in report.checks:
        print()
        print(
            f"[{check.status.value}] "
            f"{check.name}"
        )
        print("-" * 120)
        print(check.summary)

        for detail in check.details:
            print(f"- {detail}")

    print()
    print("SUMMARY")
    print("-" * 120)
    print(f"Passed:   {report.passed:,}")
    print(f"Warnings: {report.warnings:,}")
    print(f"Failures: {report.failures:,}")

    print()

    if report.failures:
        print("DATABASE DOCTOR FAILED")
    elif report.warnings:
        print("DATABASE DOCTOR PASSED WITH WARNINGS")
    else:
        print("DATABASE DOCTOR PASSED")


def main() -> int:
    report = run_database_doctor()

    print_database_doctor_report(
        report
    )

    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
