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
    "bid_tab_subcontractor_relationship_normalized_2025_v2",
)


CURRENT_RELATIONSHIP_OBJECT = (
    "bid_tab_subcontractor_relationship_current"
)


CURRENT_RELATIONSHIP_REQUIRED_COLUMNS = (
    "contract_number",
    "prime_bidder_id",
    "prime_bidder_name",
    "subcontractor_name",
    "relationship_status",
    "source_pdf",
)


CURRENT_RELATIONSHIP_BUSINESS_KEY = (
    "contract_number",
    "prime_bidder_id",
    "subcontractor_license_number",
    "subcontractor_name",
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
            "The authoritative current relationship view "
            "and normalized 2025 relationship object are present."
        ),
        details=tuple(
            REQUIRED_PRODUCTION_OBJECTS
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



def check_current_relationship_integrity(
    con: duckdb.DuckDBPyConnection,
) -> DatabaseCheck:
    available = {
        table_name
        for table_name, _ in main_schema_objects(
            con
        )
    }

    if CURRENT_RELATIONSHIP_OBJECT not in available:
        return DatabaseCheck(
            name="CURRENT_RELATIONSHIP_INTEGRITY",
            status=CheckStatus.FAIL,
            summary=(
                "The authoritative current relationship "
                "view is missing."
            ),
            details=(
                CURRENT_RELATIONSHIP_OBJECT,
            ),
        )

    columns = set(
        table_columns(
            con,
            CURRENT_RELATIONSHIP_OBJECT,
        )
    )

    missing_columns = [
        column
        for column in CURRENT_RELATIONSHIP_REQUIRED_COLUMNS
        if column not in columns
    ]

    if missing_columns:
        return DatabaseCheck(
            name="CURRENT_RELATIONSHIP_INTEGRITY",
            status=CheckStatus.FAIL,
            summary=(
                f"{len(missing_columns):,} required column(s) "
                "are missing from the current relationship view."
            ),
            details=tuple(
                missing_columns
            ),
        )

    null_checks = {
        "contract_number": con.execute(
            f"""
            SELECT COUNT(*)
            FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}
            WHERE contract_number IS NULL
               OR TRIM(contract_number) = ''
            """
        ).fetchone()[0],
        "prime_bidder_id": con.execute(
            f"""
            SELECT COUNT(*)
            FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}
            WHERE prime_bidder_id IS NULL
               OR TRIM(prime_bidder_id) = ''
            """
        ).fetchone()[0],
        "prime_bidder_name": con.execute(
            f"""
            SELECT COUNT(*)
            FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}
            WHERE prime_bidder_name IS NULL
               OR TRIM(prime_bidder_name) = ''
            """
        ).fetchone()[0],
        "subcontractor_name": con.execute(
            f"""
            SELECT COUNT(*)
            FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}
            WHERE subcontractor_name IS NULL
               OR TRIM(subcontractor_name) = ''
            """
        ).fetchone()[0],
        "source_pdf_active": con.execute(
            f"""
            SELECT COUNT(*)

            FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}

            WHERE bid_opening_date IS NOT NULL
              AND (
                    source_pdf IS NULL
                 OR TRIM(source_pdf) = ''
              )
            """
        ).fetchone()[0],
    }

    duplicate_business_keys = con.execute(
        f"""
        SELECT COUNT(*)

        FROM (
            SELECT
                contract_number,
                prime_bidder_id,
                COALESCE(
                    subcontractor_license_number,
                    ''
                ) AS subcontractor_license_number,
                subcontractor_name

            FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}

            GROUP BY
                contract_number,
                prime_bidder_id,
                COALESCE(
                    subcontractor_license_number,
                    ''
                ),
                subcontractor_name

            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    missing_status = con.execute(
        f"""
        SELECT COUNT(*)

        FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}

        WHERE relationship_status IS NULL
           OR TRIM(relationship_status) = ''
        """
    ).fetchone()[0]

    failures: list[str] = []

    for column, count in null_checks.items():
        if count:
            label = (
                "source_pdf on active rows"
                if column == "source_pdf_active"
                else column
            )

            failures.append(
                f"{label}: {count:,} missing value(s)"
            )

    if duplicate_business_keys:
        failures.append(
            "business key: "
            f"{duplicate_business_keys:,} duplicate group(s)"
        )

    if missing_status:
        failures.append(
            "relationship_status: "
            f"{missing_status:,} missing value(s)"
        )

    if failures:
        return DatabaseCheck(
            name="CURRENT_RELATIONSHIP_INTEGRITY",
            status=CheckStatus.FAIL,
            summary=(
                "The authoritative current relationship "
                "view contains integrity failures."
            ),
            details=tuple(
                failures
            ),
        )

    row_count = con.execute(
        f"""
        SELECT COUNT(*)
        FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}
        """
    ).fetchone()[0]

    return DatabaseCheck(
        name="CURRENT_RELATIONSHIP_INTEGRITY",
        status=CheckStatus.PASS,
        summary=(
            f"Validated {row_count:,} current relationship row(s) "
            "using required columns and the business key."
        ),
        details=(
            "Business key: "
            + ", ".join(
                CURRENT_RELATIONSHIP_BUSINESS_KEY
            ),
        ),
    )




def check_legacy_provenance(
    con: duckdb.DuckDBPyConnection,
) -> DatabaseCheck:
    available = {
        table_name
        for table_name, _ in main_schema_objects(
            con
        )
    }

    if CURRENT_RELATIONSHIP_OBJECT not in available:
        return DatabaseCheck(
            name="LEGACY_PROVENANCE",
            status=CheckStatus.FAIL,
            summary=(
                "The authoritative current relationship "
                "view is missing."
            ),
            details=(
                CURRENT_RELATIONSHIP_OBJECT,
            ),
        )

    legacy_rows = con.execute(
        f"""
        SELECT COUNT(*)

        FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}

        WHERE bid_opening_date IS NULL
          AND (
                source_pdf IS NULL
             OR TRIM(source_pdf) = ''
          )
        """
    ).fetchone()[0]

    pricing_eligible_legacy_rows = con.execute(
        f"""
        SELECT COUNT(*)

        FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}

        WHERE bid_opening_date IS NULL
          AND (
                source_pdf IS NULL
             OR TRIM(source_pdf) = ''
          )
          AND eligible_for_prime_pricing_analysis
        """
    ).fetchone()[0]

    disclosure_only_legacy_rows = con.execute(
        f"""
        SELECT COUNT(*)

        FROM {quote_identifier(CURRENT_RELATIONSHIP_OBJECT)}

        WHERE bid_opening_date IS NULL
          AND (
                source_pdf IS NULL
             OR TRIM(source_pdf) = ''
          )
          AND NOT eligible_for_prime_pricing_analysis
        """
    ).fetchone()[0]

    if legacy_rows:
        return DatabaseCheck(
            name="LEGACY_PROVENANCE",
            status=CheckStatus.WARN,
            summary=(
                f"{legacy_rows:,} legacy relationship row(s) "
                "lack bid-date and source-PDF provenance."
            ),
            details=(
                "Pricing eligible: "
                f"{pricing_eligible_legacy_rows:,}",
                "Disclosure only/non-pricing eligible: "
                f"{disclosure_only_legacy_rows:,}",
            ),
        )

    return DatabaseCheck(
        name="LEGACY_PROVENANCE",
        status=CheckStatus.PASS,
        summary=(
            "No legacy relationship rows are missing "
            "bid-date and source-PDF provenance."
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
            check_current_relationship_integrity(
                con
            ),
            check_legacy_provenance(
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
