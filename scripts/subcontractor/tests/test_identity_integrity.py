from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from scripts.subcontractor.database_doctor import (
    CheckStatus,
    check_identity_integrity,
)


def main() -> int:
    with TemporaryDirectory() as directory:
        database = (
            Path(directory)
            / "identity_integrity_test.duckdb"
        )

        con = duckdb.connect(
            str(database)
        )

        try:
            con.execute(
                """
                CREATE TABLE current_relationship_source
                (
                    prime_bidder_id VARCHAR,
                    prime_bidder_name VARCHAR,
                    subcontractor_license_number VARCHAR,
                    subcontractor_name VARCHAR
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

            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_disclosure_2025_alt_identity_overlay_v1
                (
                    production_identity_class VARCHAR,
                    eligible_for_prime_pricing_analysis BOOLEAN
                )
                """
            )

            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_alt_identity_audit_2025_v1
                (
                    identity_audit_status VARCHAR
                )
                """
            )

            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_alt_identity_review_2025_v1
                (
                    review_reason VARCHAR
                )
                """
            )

            con.execute(
                """
                INSERT INTO current_relationship_source
                VALUES
                (
                    'VC0000000001',
                    'PRIME CONTRACTOR',
                    '123456',
                    'SUBCONTRACTOR A'
                )
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_disclosure_2025_alt_identity_overlay_v1
                VALUES
                    ('RESOLVED', TRUE)
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_alt_identity_audit_2025_v1
                VALUES
                    ('PASSED')
                """
            )

            passing = check_identity_integrity(
                con
            )

            if passing.status != CheckStatus.PASS:
                raise RuntimeError(
                    "Expected passing identity integrity "
                    f"result, received {passing.status}: "
                    f"{passing.details}"
                )

            con.execute(
                """
                INSERT INTO current_relationship_source
                VALUES
                (
                    'VC0000000001',
                    'DIFFERENT PRIME NAME',
                    '123456',
                    'DIFFERENT SUBCONTRACTOR NAME'
                )
                """
            )

            conflicting = check_identity_integrity(
                con
            )

            if conflicting.status != CheckStatus.WARN:
                raise RuntimeError(
                    "Expected identity-name conflicts "
                    "to produce a warning."
                )

            con.execute(
                """
                INSERT INTO current_relationship_source
                VALUES
                (
                    NULL,
                    'MISSING-ID PRIME',
                    '999999',
                    'SUBCONTRACTOR B'
                )
                """
            )

            failing = check_identity_integrity(
                con
            )

            if failing.status != CheckStatus.FAIL:
                raise RuntimeError(
                    "Missing prime bidder ID "
                    "was not detected."
                )

        finally:
            con.close()

    print()
    print("IDENTITY INTEGRITY TEST PASSED")

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
