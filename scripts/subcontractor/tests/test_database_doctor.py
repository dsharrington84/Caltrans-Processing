from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from scripts.subcontractor.database_doctor import (
    CheckStatus,
    check_current_relationship_integrity,
    check_database_access,
    check_empty_tables,
    check_legacy_provenance,
    check_required_production_tables,
    check_schema_inventory,
)


def create_current_view(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        """
        CREATE TABLE current_relationship_source
        (
            contract_number VARCHAR,
            bid_opening_date TIMESTAMP,
            district BIGINT,
            prime_bidder_id VARCHAR,
            prime_bidder_name VARCHAR,
            subcontractor_license_number VARCHAR,
            subcontractor_name VARCHAR,
            relationship_status VARCHAR,
            source_pdf VARCHAR,
            eligible_for_prime_pricing_analysis BOOLEAN
        )
        """
    )

    con.execute(
        """
        CREATE VIEW
            bid_tab_subcontractor_relationship_current
        AS
        SELECT *
        FROM current_relationship_source
        """
    )


def main() -> int:
    with TemporaryDirectory() as directory:
        database = (
            Path(directory)
            / "database_doctor_test.duckdb"
        )

        con = duckdb.connect(
            str(database)
        )

        try:
            create_current_view(
                con
            )

            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_relationship_normalized_2025_v2
                (
                    contract_number VARCHAR,
                    prime_bidder_id VARCHAR
                )
                """
            )

            con.execute(
                """
                INSERT INTO current_relationship_source
                VALUES
                (
                    '07-000001',
                    TIMESTAMP '2025-01-15 00:00:00',
                    7,
                    'VC0000000001',
                    'PRIME CONTRACTOR',
                    '123456',
                    'SUBCONTRACTOR A',
                    'CERTIFIED_RELATIONSHIP',
                    'contract.pdf',
                    TRUE
                )
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_relationship_normalized_2025_v2
                VALUES
                    (
                        '07-000001',
                        'VC0000000001'
                    )
                """
            )

            access = check_database_access(
                con
            )

            schema = check_schema_inventory(
                con
            )

            empty = check_empty_tables(
                con
            )

            integrity = (
                check_current_relationship_integrity(
                    con
                )
            )

            provenance = check_legacy_provenance(
                con
            )

            required = check_required_production_tables(
                con
            )

            expected = {
                "DATABASE_ACCESS": CheckStatus.PASS,
                "SCHEMA_INVENTORY": CheckStatus.PASS,
                "EMPTY_TABLES": CheckStatus.PASS,
                "CURRENT_RELATIONSHIP_INTEGRITY": CheckStatus.PASS,
                "LEGACY_PROVENANCE": CheckStatus.PASS,
                "REQUIRED_PRODUCTION_TABLES": CheckStatus.PASS,
            }

            actual = {
                access.name: access.status,
                schema.name: schema.status,
                empty.name: empty.status,
                integrity.name: integrity.status,
                provenance.name: provenance.status,
                required.name: required.status,
            }

            if actual != expected:
                raise RuntimeError(
                    f"Unexpected check statuses: {actual}"
                )

            con.execute(
                """
                INSERT INTO current_relationship_source
                VALUES
                (
                    '07-000001',
                    TIMESTAMP '2025-01-15 00:00:00',
                    7,
                    'VC0000000001',
                    'PRIME CONTRACTOR',
                    '123456',
                    'SUBCONTRACTOR A',
                    'CERTIFIED_RELATIONSHIP',
                    'contract.pdf',
                    TRUE
                )
                """
            )

            duplicate_result = (
                check_current_relationship_integrity(
                    con
                )
            )

            if (
                duplicate_result.status
                != CheckStatus.FAIL
            ):
                raise RuntimeError(
                    "Duplicate current relationship "
                    "business key was not detected."
                )

            con.execute(
                """
                DELETE FROM current_relationship_source
                """
            )

            con.execute(
                """
                INSERT INTO current_relationship_source
                VALUES
                (
                    '07-LEGACY',
                    NULL,
                    NULL,
                    'VC0000000002',
                    'LEGACY PRIME CONTRACTOR',
                    '654321',
                    'LEGACY SUBCONTRACTOR',
                    'CERTIFIED_RELATIONSHIP',
                    NULL,
                    TRUE
                )
                """
            )

            legacy_integrity = (
                check_current_relationship_integrity(
                    con
                )
            )

            if (
                legacy_integrity.status
                != CheckStatus.PASS
            ):
                raise RuntimeError(
                    "Legacy provenance row incorrectly "
                    "failed active relationship integrity."
                )

            legacy_provenance = (
                check_legacy_provenance(
                    con
                )
            )

            if (
                legacy_provenance.status
                != CheckStatus.WARN
            ):
                raise RuntimeError(
                    "Legacy provenance warning "
                    "was not detected."
                )

        finally:
            con.close()

    print()
    print("DATABASE DOCTOR TEST PASSED")

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
