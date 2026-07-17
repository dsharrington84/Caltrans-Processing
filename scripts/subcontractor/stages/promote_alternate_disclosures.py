from __future__ import annotations

import pandas as pd


from scripts.subcontractor.stage_runtime import (
    Stage,
    run_stage,
)

from scripts.subcontractor.config import PipelineConfig
from scripts.subcontractor.database import (
    connect_database,
    ensure_target_objects_absent,
    quote_identifier,
    require_objects,
)
from scripts.subcontractor.logging_utils import (
    configure_logging,
    log_key_value,
    log_section,
    log_subsection,
)


SOURCE_TABLE = (
    "bid_tab_subcontractor_disclosure_"
    "2025_alt_identity_overlay_v1"
)

PROMOTED_TABLE = (
    "bid_tab_subcontractor_disclosure_"
    "2025_alt_promoted_v1"
)

PROMOTION_AUDIT_TABLE = (
    "bid_tab_subcontractor_alt_"
    "promotion_audit_2025_v1"
)


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "promote_alternate_disclosures",
    )

    log_section(
        logger,
        "ALTERNATE DISCLOSURE PROMOTION",
        width=160,
    )

    read_connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        read_connection,
        [SOURCE_TABLE],
    )

    source_q = quote_identifier(
        SOURCE_TABLE
    )

    source = read_connection.execute(
        f"""
        SELECT *

        FROM {source_q}

        ORDER BY
            contract_number,
            bid_rank,
            disclosure_sequence
        """
    ).fetchdf()

    read_connection.close()

    if source.empty:
        raise RuntimeError(
            "Identity-overlay source table is empty."
        )

    allowed_promotion_statuses = {
        "READY_FOR_PROMOTION",
        "READY_WITH_IDENTITY_GAP",
    }

    invalid_status_rows = source[
        ~source["promotion_status"].isin(
            allowed_promotion_statuses
        )
    ]

    if not invalid_status_rows.empty:
        raise RuntimeError(
            "Source contains rows that are "
            "not eligible for promotion."
        )

    duplicate_ids = int(
        source[
            "disclosure_id"
        ].duplicated().sum()
    )

    if duplicate_ids:
        raise RuntimeError(
            f"Duplicate disclosure IDs found: "
            f"{duplicate_ids:,}"
        )

    source[
        "promoted_record_status"
    ] = "PROMOTED"

    source.loc[
        source["promotion_status"]
        == "READY_WITH_IDENTITY_GAP",
        "promoted_record_status",
    ] = "PROMOTED_WITH_IDENTITY_GAP"

    source[
        "promotion_basis"
    ] = (
        "ALTERNATE_LAYOUT_STAGE2_V2_"
        "CERTIFIED_IDENTITY_OVERLAY_V1"
    )

    source[
        "source_pipeline"
    ] = (
        "2025_INCREMENTAL_ALTERNATE_LAYOUT"
    )

    source[
        "source_certification_table"
    ] = (
        "bid_tab_subcontractor_disclosure_"
        "2025_alt_certified_v1"
    )

    source[
        "source_identity_overlay_table"
    ] = SOURCE_TABLE

    promotion_audit = (
        source.groupby(
            [
                "contract_number",
                "bid_rank",
                "prime_bidder_id",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            prime_bidder_name=(
                "prime_bidder_name",
                "first",
            ),
            disclosure_rows=(
                "disclosure_id",
                "count",
            ),
            unique_disclosure_ids=(
                "disclosure_id",
                "nunique",
            ),
            unique_subcontractor_names=(
                "subcontractor_name",
                "nunique",
            ),
            unique_subcontractor_licenses=(
                "license_number",
                "nunique",
            ),
            first_source_page=(
                "source_page_number",
                "min",
            ),
            last_source_page=(
                "source_page_number",
                "max",
            ),
            identity_overlay_status=(
                "identity_overlay_status",
                "first",
            ),
            promotion_status=(
                "promotion_status",
                "first",
            ),
            promoted_record_status=(
                "promoted_record_status",
                "first",
            ),
        )
    )

    promotion_audit[
        "duplicate_disclosure_ids"
    ] = (
        promotion_audit[
            "disclosure_rows"
        ]
        - promotion_audit[
            "unique_disclosure_ids"
        ]
    )

    promotion_audit[
        "promotion_audit_status"
    ] = "PASSED"

    promotion_audit.loc[
        promotion_audit[
            "duplicate_disclosure_ids"
        ] != 0,
        "promotion_audit_status",
    ] = "FAILED_DUPLICATE_IDS"

    promotion_audit.loc[
        ~promotion_audit[
            "promotion_status"
        ].isin(
            allowed_promotion_statuses
        ),
        "promotion_audit_status",
    ] = "FAILED_INVALID_STATUS"

    audit_failures = int(
        (
            promotion_audit[
                "promotion_audit_status"
            ]
            != "PASSED"
        ).sum()
    )

    if audit_failures:
        raise RuntimeError(
            f"Promotion audit failures: "
            f"{audit_failures:,}"
        )

    write_connection = connect_database(
        config.database_path,
        read_only=False,
    )

    ensure_target_objects_absent(
        write_connection,
        [
            PROMOTED_TABLE,
            PROMOTION_AUDIT_TABLE,
        ],
    )

    write_connection.register(
        "promoted_frame",
        source,
    )

    write_connection.register(
        "promotion_audit_frame",
        promotion_audit,
    )

    promoted_q = quote_identifier(
        PROMOTED_TABLE
    )

    audit_q = quote_identifier(
        PROMOTION_AUDIT_TABLE
    )

    write_connection.execute(
        f"""
        CREATE TABLE {promoted_q} AS

        SELECT *
        FROM promoted_frame
        """
    )

    write_connection.execute(
        f"""
        CREATE TABLE {audit_q} AS

        SELECT *
        FROM promotion_audit_frame
        """
    )

    inserted_rows = int(
        write_connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {promoted_q}
            """
        ).fetchone()[0]
    )

    inserted_unique_ids = int(
        write_connection.execute(
            f"""
            SELECT COUNT(
                DISTINCT disclosure_id
            )
            FROM {promoted_q}
            """
        ).fetchone()[0]
    )

    inserted_contracts = int(
        write_connection.execute(
            f"""
            SELECT COUNT(
                DISTINCT contract_number
            )
            FROM {promoted_q}
            """
        ).fetchone()[0]
    )

    inserted_blocks = int(
        write_connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {audit_q}
            """
        ).fetchone()[0]
    )

    write_connection.unregister(
        "promoted_frame"
    )

    write_connection.unregister(
        "promotion_audit_frame"
    )

    write_connection.close()

    fully_promoted_rows = int(
        (
            source[
                "promoted_record_status"
            ]
            == "PROMOTED"
        ).sum()
    )

    promoted_gap_rows = int(
        (
            source[
                "promoted_record_status"
            ]
            == "PROMOTED_WITH_IDENTITY_GAP"
        ).sum()
    )

    fully_promoted_blocks = int(
        (
            promotion_audit[
                "promoted_record_status"
            ]
            == "PROMOTED"
        ).sum()
    )

    promoted_gap_blocks = int(
        (
            promotion_audit[
                "promoted_record_status"
            ]
            == "PROMOTED_WITH_IDENTITY_GAP"
        ).sum()
    )

    log_key_value(
        logger,
        "Source rows",
        len(source),
    )

    log_key_value(
        logger,
        "Promoted rows",
        fully_promoted_rows,
    )

    log_key_value(
        logger,
        "Promoted rows with identity gap",
        promoted_gap_rows,
    )

    log_key_value(
        logger,
        "Promoted contracts",
        inserted_contracts,
    )

    log_key_value(
        logger,
        "Promoted bidder blocks",
        inserted_blocks,
    )

    log_key_value(
        logger,
        "Fully promoted bidder blocks",
        fully_promoted_blocks,
    )

    log_key_value(
        logger,
        "Promoted bidder blocks with identity gap",
        promoted_gap_blocks,
    )

    log_key_value(
        logger,
        "Inserted rows",
        inserted_rows,
    )

    log_key_value(
        logger,
        "Inserted unique disclosure IDs",
        inserted_unique_ids,
    )

    log_key_value(
        logger,
        "Promotion audit failures",
        audit_failures,
    )

    log_key_value(
        logger,
        "Promoted table",
        PROMOTED_TABLE,
    )

    log_key_value(
        logger,
        "Promotion audit table",
        PROMOTION_AUDIT_TABLE,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    log_subsection(
        logger,
        "PROMOTED CONTRACT SUMMARY",
        width=160,
    )

    contract_summary = (
        source.groupby(
            "contract_number",
            as_index=False,
        )
        .agg(
            disclosure_rows=(
                "disclosure_id",
                "count",
            ),
            bidder_blocks=(
                "bid_rank",
                "nunique",
            ),
            identity_gap_rows=(
                "promoted_record_status",
                lambda values: int(
                    (
                        values
                        == (
                            "PROMOTED_WITH_"
                            "IDENTITY_GAP"
                        )
                    ).sum()
                ),
            ),
        )
    )

    logger.info(
        "%-13s %16s %14s %18s",
        "Contract",
        "Disclosure rows",
        "Bidder blocks",
        "Identity-gap rows",
    )

    logger.info("-" * 70)

    for row in contract_summary.itertuples(
        index=False,
    ):
        logger.info(
            "%-13s %16d %14d %18d",
            row.contract_number,
            int(row.disclosure_rows),
            int(row.bidder_blocks),
            int(row.identity_gap_rows),
        )

    if inserted_rows != len(source):
        raise RuntimeError(
            "Promoted-table row count mismatch."
        )

    if inserted_unique_ids != len(source):
        raise RuntimeError(
            "Promoted disclosure IDs are not unique."
        )

    logger.info("")
    logger.info(
        "ALTERNATE DISCLOSURE PROMOTION PASSED"
    )

    return 0



class PromoteAlternateDisclosuresStage(Stage):
    name = "promote-alternate-disclosures"
    description = (
        "Promote certified alternate-layout "
        "subcontractor disclosures."
    )
    writes_database = True
    backup_reason = (
        "before_2025_alt_disclosure_promotion"
    )

    def open_connection(self) -> None:
        # The legacy run() function still owns its DuckDB
        # connection during this transitional migration.
        self.connection = None

    def execute(self) -> dict[str, object]:
        legacy_config = PipelineConfig.load()

        result = run(
            legacy_config
        )

        if isinstance(result, dict):
            return result

        return {
            "legacy_return_value": result,
        }




def main() -> int:
    return run_stage(
        PromoteAlternateDisclosuresStage
    )


if __name__ == "__main__":
    raise SystemExit(main())
