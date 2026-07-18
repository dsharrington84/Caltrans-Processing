from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from scripts.subcontractor.database_doctor import (
    CheckStatus,
    check_promotion_reconciliation,
)


def main() -> int:
    with TemporaryDirectory() as directory:
        database = (
            Path(directory)
            / "promotion_reconciliation_test.duckdb"
        )

        con = duckdb.connect(
            str(database)
        )

        try:
            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_disclosure_2025_alt_identity_overlay_v1
                (
                    disclosure_id VARCHAR,
                    contract_number VARCHAR
                )
                """
            )

            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_disclosure_2025_alt_promoted_v1
                (
                    disclosure_id VARCHAR,
                    contract_number VARCHAR
                )
                """
            )

            con.execute(
                """
                CREATE TABLE
                    bid_tab_subcontractor_alt_promotion_audit_2025_v1
                (
                    promotion_audit_status VARCHAR,
                    disclosure_rows BIGINT,
                    duplicate_disclosure_ids BIGINT
                )
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_disclosure_2025_alt_identity_overlay_v1
                VALUES
                    ('DISC-1', '07-000001'),
                    ('DISC-2', '07-000001')
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_disclosure_2025_alt_promoted_v1
                VALUES
                    ('DISC-1', '07-000001'),
                    ('DISC-2', '07-000001')
                """
            )

            con.execute(
                """
                INSERT INTO
                    bid_tab_subcontractor_alt_promotion_audit_2025_v1
                VALUES
                    ('PASSED', 2, 0)
                """
            )

            passing = check_promotion_reconciliation(
                con
            )

            if passing.status != CheckStatus.PASS:
                raise RuntimeError(
                    "Expected passing promotion reconciliation, "
                    f"received {passing.status}: "
                    f"{passing.details}"
                )

            con.execute(
                """
                UPDATE
                    bid_tab_subcontractor_alt_promotion_audit_2025_v1
                SET
                    promotion_audit_status = 'FAILED'
                """
            )

            failing = check_promotion_reconciliation(
                con
            )

            if failing.status != CheckStatus.FAIL:
                raise RuntimeError(
                    "Failed promotion audit was not detected."
                )

        finally:
            con.close()

    print()
    print("PROMOTION RECONCILIATION TEST PASSED")

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
