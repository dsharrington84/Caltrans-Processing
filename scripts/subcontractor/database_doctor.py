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




PROMOTION_IDENTITY_OVERLAY_OBJECT = (
    "bid_tab_subcontractor_"
    "disclosure_2025_alt_identity_overlay_v1"
)

PROMOTION_PROMOTED_OBJECT = (
    "bid_tab_subcontractor_"
    "disclosure_2025_alt_promoted_v1"
)

PROMOTION_AUDIT_OBJECT = (
    "bid_tab_subcontractor_"
    "alt_promotion_audit_2025_v1"
)


def object_columns(
    con: duckdb.DuckDBPyConnection,
    object_name: str,
) -> set[str]:
    return set(
        table_columns(
            con,
            object_name,
        )
    )


def object_row_count(
    con: duckdb.DuckDBPyConnection,
    object_name: str,
) -> int:
    return int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM {quote_identifier(object_name)}
            """
        ).fetchone()[0]
    )


def check_promotion_reconciliation(
    con: duckdb.DuckDBPyConnection,
) -> DatabaseCheck:
    available = {
        table_name
        for table_name, _ in main_schema_objects(
            con
        )
    }

    required_objects = (
        PROMOTION_IDENTITY_OVERLAY_OBJECT,
        PROMOTION_PROMOTED_OBJECT,
        PROMOTION_AUDIT_OBJECT,
    )

    missing_objects = [
        name
        for name in required_objects
        if name not in available
    ]

    if missing_objects:
        return DatabaseCheck(
            name="PROMOTION_RECONCILIATION",
            status=CheckStatus.FAIL,
            summary=(
                f"{len(missing_objects):,} required promotion "
                "object(s) are missing."
            ),
            details=tuple(
                missing_objects
            ),
        )

    overlay_columns = object_columns(
        con,
        PROMOTION_IDENTITY_OVERLAY_OBJECT,
    )

    promoted_columns = object_columns(
        con,
        PROMOTION_PROMOTED_OBJECT,
    )

    audit_columns = object_columns(
        con,
        PROMOTION_AUDIT_OBJECT,
    )

    overlay_rows = object_row_count(
        con,
        PROMOTION_IDENTITY_OVERLAY_OBJECT,
    )

    promoted_rows = object_row_count(
        con,
        PROMOTION_PROMOTED_OBJECT,
    )

    failures: list[str] = []
    warnings: list[str] = []
    details: list[str] = [
        f"Identity overlay rows: {overlay_rows:,}",
        f"Promoted rows: {promoted_rows:,}",
    ]

    if promoted_rows > overlay_rows:
        failures.append(
            "Promoted rows exceed identity-overlay rows: "
            f"{promoted_rows:,} > {overlay_rows:,}"
        )

    elif promoted_rows < overlay_rows:
        warnings.append(
            "Identity-overlay rows exceed promoted rows by "
            f"{overlay_rows - promoted_rows:,}."
        )

    else:
        details.append(
            "Identity overlay and promoted row counts reconcile."
        )

    if "promotion_audit_status" in audit_columns:
        failed_audit_rows = int(
            con.execute(
                f"""
                SELECT COUNT(*)

                FROM {quote_identifier(PROMOTION_AUDIT_OBJECT)}

                WHERE promotion_audit_status IS NULL
                   OR UPPER(
                        TRIM(
                            CAST(
                                promotion_audit_status
                                AS VARCHAR
                            )
                        )
                   ) <> 'PASSED'
                """
            ).fetchone()[0]
        )

        if failed_audit_rows:
            failures.append(
                f"{failed_audit_rows:,} promotion audit row(s) "
                "are not marked PASSED."
            )
        else:
            details.append(
                "All promotion audit rows are marked PASSED."
            )
    else:
        warnings.append(
            "promotion_audit_status is not available "
            "in the promotion audit object."
        )

    if "duplicate_disclosure_ids" in audit_columns:
        duplicate_audit_ids = int(
            con.execute(
                f"""
                SELECT COALESCE(
                    SUM(
                        CAST(
                            duplicate_disclosure_ids
                            AS BIGINT
                        )
                    ),
                    0
                )

                FROM {quote_identifier(PROMOTION_AUDIT_OBJECT)}
                """
            ).fetchone()[0]
        )

        if duplicate_audit_ids:
            failures.append(
                f"Promotion audit reports "
                f"{duplicate_audit_ids:,} duplicate "
                "disclosure ID(s)."
            )
        else:
            details.append(
                "Promotion audit reports no duplicate "
                "disclosure IDs."
            )

    disclosure_id_candidates = (
        "disclosure_id",
        "subcontractor_disclosure_id",
        "promoted_disclosure_id",
    )

    promoted_disclosure_id = next(
        (
            candidate
            for candidate in disclosure_id_candidates
            if candidate in promoted_columns
        ),
        None,
    )

    if promoted_disclosure_id is not None:
        duplicate_promoted_ids = int(
            con.execute(
                f"""
                SELECT COUNT(*)

                FROM (
                    SELECT
                        {quote_identifier(promoted_disclosure_id)}

                    FROM {
                        quote_identifier(
                            PROMOTION_PROMOTED_OBJECT
                        )
                    }

                    WHERE {
                        quote_identifier(
                            promoted_disclosure_id
                        )
                    } IS NOT NULL

                    GROUP BY
                        {
                            quote_identifier(
                                promoted_disclosure_id
                            )
                        }

                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
        )

        if duplicate_promoted_ids:
            failures.append(
                f"{duplicate_promoted_ids:,} duplicated "
                f"{promoted_disclosure_id} value(s) exist "
                "in promoted disclosures."
            )
        else:
            details.append(
                f"No duplicate {promoted_disclosure_id} "
                "values exist in promoted disclosures."
            )
    else:
        warnings.append(
            "No recognized disclosure-ID column exists "
            "in the promoted disclosure object."
        )

    if "disclosure_rows" in audit_columns:
        audited_disclosure_rows = int(
            con.execute(
                f"""
                SELECT COALESCE(
                    SUM(
                        CAST(
                            disclosure_rows
                            AS BIGINT
                        )
                    ),
                    0
                )

                FROM {quote_identifier(PROMOTION_AUDIT_OBJECT)}
                """
            ).fetchone()[0]
        )

        details.append(
            "Promotion audit disclosure rows: "
            f"{audited_disclosure_rows:,}"
        )

        if audited_disclosure_rows != promoted_rows:
            failures.append(
                "Promotion audit disclosure total does not "
                "match promoted row count: "
                f"{audited_disclosure_rows:,} != "
                f"{promoted_rows:,}"
            )
    else:
        warnings.append(
            "disclosure_rows is not available in the "
            "promotion audit object."
        )

    common_id = next(
        (
            candidate
            for candidate in disclosure_id_candidates
            if (
                candidate in overlay_columns
                and candidate in promoted_columns
            )
        ),
        None,
    )

    if common_id is not None:
        missing_from_promoted = int(
            con.execute(
                f"""
                SELECT COUNT(*)

                FROM (
                    SELECT DISTINCT
                        {quote_identifier(common_id)}
                    FROM {
                        quote_identifier(
                            PROMOTION_IDENTITY_OVERLAY_OBJECT
                        )
                    }
                    WHERE {quote_identifier(common_id)}
                        IS NOT NULL

                    EXCEPT

                    SELECT DISTINCT
                        {quote_identifier(common_id)}
                    FROM {
                        quote_identifier(
                            PROMOTION_PROMOTED_OBJECT
                        )
                    }
                    WHERE {quote_identifier(common_id)}
                        IS NOT NULL
                )
                """
            ).fetchone()[0]
        )

        unexpected_promoted = int(
            con.execute(
                f"""
                SELECT COUNT(*)

                FROM (
                    SELECT DISTINCT
                        {quote_identifier(common_id)}
                    FROM {
                        quote_identifier(
                            PROMOTION_PROMOTED_OBJECT
                        )
                    }
                    WHERE {quote_identifier(common_id)}
                        IS NOT NULL

                    EXCEPT

                    SELECT DISTINCT
                        {quote_identifier(common_id)}
                    FROM {
                        quote_identifier(
                            PROMOTION_IDENTITY_OVERLAY_OBJECT
                        )
                    }
                    WHERE {quote_identifier(common_id)}
                        IS NOT NULL
                )
                """
            ).fetchone()[0]
        )

        if unexpected_promoted:
            failures.append(
                f"{unexpected_promoted:,} promoted "
                f"{common_id} value(s) do not exist in "
                "the identity overlay."
            )

        if missing_from_promoted:
            warnings.append(
                f"{missing_from_promoted:,} identity-overlay "
                f"{common_id} value(s) were not promoted."
            )

        if (
            not missing_from_promoted
            and not unexpected_promoted
        ):
            details.append(
                f"Identity overlay and promoted {common_id} "
                "sets reconcile."
            )
    else:
        warnings.append(
            "No shared recognized disclosure-ID column "
            "exists between identity overlay and promoted data."
        )

    if failures:
        return DatabaseCheck(
            name="PROMOTION_RECONCILIATION",
            status=CheckStatus.FAIL,
            summary=(
                "Promotion-stage reconciliation found "
                f"{len(failures):,} failure(s)."
            ),
            details=tuple(
                failures
                + warnings
                + details
            ),
        )

    if warnings:
        return DatabaseCheck(
            name="PROMOTION_RECONCILIATION",
            status=CheckStatus.WARN,
            summary=(
                "Promotion-stage reconciliation completed "
                f"with {len(warnings):,} warning(s)."
            ),
            details=tuple(
                warnings
                + details
            ),
        )

    return DatabaseCheck(
        name="PROMOTION_RECONCILIATION",
        status=CheckStatus.PASS,
        summary=(
            "Promotion-stage row counts, audit results, "
            "and disclosure identifiers reconcile."
        ),
        details=tuple(
            details
        ),
    )




IDENTITY_OVERLAY_OBJECT = (
    "bid_tab_subcontractor_"
    "disclosure_2025_alt_identity_overlay_v1"
)

IDENTITY_AUDIT_OBJECT = (
    "bid_tab_subcontractor_"
    "alt_identity_audit_2025_v1"
)

IDENTITY_REVIEW_OBJECT = (
    "bid_tab_subcontractor_"
    "alt_identity_review_2025_v1"
)


def check_identity_integrity(
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
            name="IDENTITY_INTEGRITY",
            status=CheckStatus.FAIL,
            summary=(
                "The authoritative current relationship "
                "view is missing."
            ),
            details=(
                CURRENT_RELATIONSHIP_OBJECT,
            ),
        )

    current_columns = object_columns(
        con,
        CURRENT_RELATIONSHIP_OBJECT,
    )

    required_current_columns = {
        "prime_bidder_id",
        "prime_bidder_name",
        "subcontractor_license_number",
        "subcontractor_name",
    }

    missing_current_columns = sorted(
        required_current_columns
        - current_columns
    )

    if missing_current_columns:
        return DatabaseCheck(
            name="IDENTITY_INTEGRITY",
            status=CheckStatus.FAIL,
            summary=(
                f"{len(missing_current_columns):,} identity "
                "column(s) are missing from the current "
                "relationship view."
            ),
            details=tuple(
                missing_current_columns
            ),
        )

    failures: list[str] = []
    warnings: list[str] = []
    details: list[str] = []

    missing_prime_bidder_id = int(
        con.execute(
            f"""
            SELECT COUNT(*)

            FROM {
                quote_identifier(
                    CURRENT_RELATIONSHIP_OBJECT
                )
            }

            WHERE prime_bidder_id IS NULL
               OR TRIM(prime_bidder_id) = ''
            """
        ).fetchone()[0]
    )

    missing_prime_bidder_name = int(
        con.execute(
            f"""
            SELECT COUNT(*)

            FROM {
                quote_identifier(
                    CURRENT_RELATIONSHIP_OBJECT
                )
            }

            WHERE prime_bidder_name IS NULL
               OR TRIM(prime_bidder_name) = ''
            """
        ).fetchone()[0]
    )

    missing_subcontractor_name = int(
        con.execute(
            f"""
            SELECT COUNT(*)

            FROM {
                quote_identifier(
                    CURRENT_RELATIONSHIP_OBJECT
                )
            }

            WHERE subcontractor_name IS NULL
               OR TRIM(subcontractor_name) = ''
            """
        ).fetchone()[0]
    )

    missing_subcontractor_license = int(
        con.execute(
            f"""
            SELECT COUNT(*)

            FROM {
                quote_identifier(
                    CURRENT_RELATIONSHIP_OBJECT
                )
            }

            WHERE subcontractor_license_number IS NULL
               OR TRIM(
                    CAST(
                        subcontractor_license_number
                        AS VARCHAR
                    )
               ) = ''
            """
        ).fetchone()[0]
    )

    if missing_prime_bidder_id:
        failures.append(
            "prime_bidder_id: "
            f"{missing_prime_bidder_id:,} missing value(s)"
        )

    if missing_prime_bidder_name:
        failures.append(
            "prime_bidder_name: "
            f"{missing_prime_bidder_name:,} missing value(s)"
        )

    if missing_subcontractor_name:
        failures.append(
            "subcontractor_name: "
            f"{missing_subcontractor_name:,} missing value(s)"
        )

    if missing_subcontractor_license:
        warnings.append(
            "subcontractor_license_number: "
            f"{missing_subcontractor_license:,} missing value(s)"
        )

    prime_name_conflicts = int(
        con.execute(
            f"""
            SELECT COUNT(*)

            FROM (
                SELECT
                    prime_bidder_id

                FROM {
                    quote_identifier(
                        CURRENT_RELATIONSHIP_OBJECT
                    )
                }

                WHERE prime_bidder_id IS NOT NULL
                  AND TRIM(prime_bidder_id) <> ''
                  AND prime_bidder_name IS NOT NULL
                  AND TRIM(prime_bidder_name) <> ''

                GROUP BY
                    prime_bidder_id

                HAVING COUNT(
                    DISTINCT UPPER(
                        TRIM(prime_bidder_name)
                    )
                ) > 1
            )
            """
        ).fetchone()[0]
    )

    if prime_name_conflicts:
        warnings.append(
            f"{prime_name_conflicts:,} prime bidder ID(s) "
            "map to multiple exact normalized names."
        )
    else:
        details.append(
            "Prime bidder IDs map to one exact "
            "normalized name each."
        )

    license_name_conflicts = int(
        con.execute(
            f"""
            SELECT COUNT(*)

            FROM (
                SELECT
                    subcontractor_license_number

                FROM {
                    quote_identifier(
                        CURRENT_RELATIONSHIP_OBJECT
                    )
                }

                WHERE subcontractor_license_number IS NOT NULL
                  AND TRIM(
                        CAST(
                            subcontractor_license_number
                            AS VARCHAR
                        )
                  ) <> ''
                  AND subcontractor_name IS NOT NULL
                  AND TRIM(subcontractor_name) <> ''

                GROUP BY
                    subcontractor_license_number

                HAVING COUNT(
                    DISTINCT UPPER(
                        TRIM(subcontractor_name)
                    )
                ) > 1
            )
            """
        ).fetchone()[0]
    )

    if license_name_conflicts:
        warnings.append(
            f"{license_name_conflicts:,} subcontractor "
            "license number(s) map to multiple exact "
            "normalized names."
        )
    else:
        details.append(
            "Subcontractor licenses map to one exact "
            "normalized name each."
        )

    if IDENTITY_OVERLAY_OBJECT in available:
        overlay_columns = object_columns(
            con,
            IDENTITY_OVERLAY_OBJECT,
        )

        overlay_rows = object_row_count(
            con,
            IDENTITY_OVERLAY_OBJECT,
        )

        details.append(
            f"Identity overlay rows: {overlay_rows:,}"
        )

        if "production_identity_class" in overlay_columns:
            identity_gap_rows = int(
                con.execute(
                    f"""
                    SELECT COUNT(*)

                    FROM {
                        quote_identifier(
                            IDENTITY_OVERLAY_OBJECT
                        )
                    }

                    WHERE UPPER(
                        TRIM(
                            CAST(
                                production_identity_class
                                AS VARCHAR
                            )
                        )
                    ) LIKE '%GAP%'
                    """
                ).fetchone()[0]
            )

            if identity_gap_rows:
                warnings.append(
                    f"{identity_gap_rows:,} identity-overlay "
                    "row(s) remain classified as identity gaps."
                )
            else:
                details.append(
                    "No identity-overlay rows remain "
                    "classified as identity gaps."
                )

        if (
            "eligible_for_prime_pricing_analysis"
            in overlay_columns
        ):
            ineligible_rows = int(
                con.execute(
                    f"""
                    SELECT COUNT(*)

                    FROM {
                        quote_identifier(
                            IDENTITY_OVERLAY_OBJECT
                        )
                    }

                    WHERE NOT COALESCE(
                        eligible_for_prime_pricing_analysis,
                        FALSE
                    )
                    """
                ).fetchone()[0]
            )

            details.append(
                "Identity-overlay rows not eligible for "
                f"prime pricing analysis: {ineligible_rows:,}"
            )
    else:
        warnings.append(
            "Alternate identity overlay object is missing."
        )

    if IDENTITY_AUDIT_OBJECT in available:
        audit_columns = object_columns(
            con,
            IDENTITY_AUDIT_OBJECT,
        )

        audit_rows = object_row_count(
            con,
            IDENTITY_AUDIT_OBJECT,
        )

        details.append(
            f"Identity audit rows: {audit_rows:,}"
        )

        status_column = next(
            (
                column
                for column in (
                    "identity_audit_status",
                    "audit_status",
                    "status",
                )
                if column in audit_columns
            ),
            None,
        )

        if status_column is not None:
            failed_audit_rows = int(
                con.execute(
                    f"""
                    SELECT COUNT(*)

                    FROM {
                        quote_identifier(
                            IDENTITY_AUDIT_OBJECT
                        )
                    }

                    WHERE {
                        quote_identifier(
                            status_column
                        )
                    } IS NULL
                       OR UPPER(
                            TRIM(
                                CAST(
                                    {
                                        quote_identifier(
                                            status_column
                                        )
                                    }
                                    AS VARCHAR
                                )
                            )
                       ) NOT IN (
                            'PASSED',
                            'PASS',
                            'READY',
                            'RESOLVED'
                       )
                    """
                ).fetchone()[0]
            )

            if failed_audit_rows:
                warnings.append(
                    f"{failed_audit_rows:,} identity audit "
                    "row(s) are not in a passing status."
                )
    else:
        warnings.append(
            "Alternate identity audit object is missing."
        )

    if IDENTITY_REVIEW_OBJECT in available:
        review_rows = object_row_count(
            con,
            IDENTITY_REVIEW_OBJECT,
        )

        if review_rows:
            warnings.append(
                f"{review_rows:,} identity review row(s) "
                "remain in the review table."
            )
        else:
            details.append(
                "Identity review backlog is empty."
            )
    else:
        warnings.append(
            "Alternate identity review object is missing."
        )

    if failures:
        return DatabaseCheck(
            name="IDENTITY_INTEGRITY",
            status=CheckStatus.FAIL,
            summary=(
                "Identity validation found "
                f"{len(failures):,} failure(s)."
            ),
            details=tuple(
                failures
                + warnings
                + details
            ),
        )

    if warnings:
        return DatabaseCheck(
            name="IDENTITY_INTEGRITY",
            status=CheckStatus.WARN,
            summary=(
                "Identity validation completed with "
                f"{len(warnings):,} warning(s)."
            ),
            details=tuple(
                warnings
                + details
            ),
        )

    return DatabaseCheck(
        name="IDENTITY_INTEGRITY",
        status=CheckStatus.PASS,
        summary=(
            "Prime bidder and subcontractor identity "
            "mappings passed validation."
        ),
        details=tuple(
            details
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
            check_promotion_reconciliation(
                con
            ),
            check_identity_integrity(
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
