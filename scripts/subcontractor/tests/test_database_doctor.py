from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from scripts.subcontractor.database_doctor import (
    CheckStatus,
    check_database_access,
    check_duplicate_relationship_ids,
    check_empty_tables,
    check_required_production_tables,
    check_schema_inventory,
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
            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_relationship_current
                (
                    relationship_id VARCHAR,
                    contract_number VARCHAR
                )
                """
            )

            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_relationship_current_v2
                (
                    relationship_id VARCHAR,
                    contract_number VARCHAR
                )
                """
            )

            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_relationship_normalized_2025_v2
                (
                    relationship_id VARCHAR,
                    contract_number VARCHAR
                )
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_relationship_current

                VALUES
                    ('REL-1', '07-000001')
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_relationship_current_v2

                VALUES
                    ('REL-1', '07-000001')
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_relationship_normalized_2025_v2

                VALUES
                    ('REL-1', '07-000001')
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

            duplicates = check_duplicate_relationship_ids(
                con
            )

            required = check_required_production_tables(
                con
            )

            expected = {
                "DATABASE_ACCESS": CheckStatus.PASS,
                "SCHEMA_INVENTORY": CheckStatus.PASS,
                "EMPTY_TABLES": CheckStatus.PASS,
                "DUPLICATE_RELATIONSHIP_IDS": CheckStatus.PASS,
                "REQUIRED_PRODUCTION_TABLES": CheckStatus.PASS,
            }

            actual = {
                access.name: access.status,
                schema.name: schema.status,
                empty.name: empty.status,
                duplicates.name: duplicates.status,
                required.name: required.status,
            }

            if actual != expected:
                raise RuntimeError(
                    f"Unexpected check statuses: {actual}"
                )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_relationship_current

                VALUES
                    ('REL-1', '07-000002')
                """
            )

            duplicate_result = (
                check_duplicate_relationship_ids(
                    con
                )
            )

            if (
                duplicate_result.status
                != CheckStatus.FAIL
            ):
                raise RuntimeError(
                    "Duplicate relationship ID "
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
