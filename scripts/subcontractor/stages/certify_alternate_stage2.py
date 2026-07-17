from __future__ import annotations

import pandas as pd

from scripts.subcontractor.config import PipelineConfig
from scripts.subcontractor.database import (
    connect_database,
    create_backup,
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
    "2025_alt_stage2_v2"
)

CERTIFIED_TABLE = (
    "bid_tab_subcontractor_disclosure_"
    "2025_alt_certified_v1"
)

CERTIFICATION_AUDIT_TABLE = (
    "bid_tab_subcontractor_alt_"
    "certification_audit_2025_v1"
)


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "certify_alternate_stage2",
    )

    log_section(
        logger,
        "ALTERNATE-LAYOUT STAGE 2 CERTIFICATION",
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
            "The alternate Stage 2 source table is empty."
        )

    source["prime_bidder_name_resolved"] = (
        source["prime_bidder_name"]
        .notna()
        & (
            source["prime_bidder_name"]
            .astype(str)
            .str.strip()
            != ""
        )
    )

    source["structural_validation_passed"] = (
        source["row_parse_status"]
        == "READY_FOR_QA"
    ) & source["disclosure_id"].notna() \
      & source["contract_number"].notna() \
      & source["bid_rank"].notna() \
      & source["prime_bidder_id"].notna() \
      & source["subcontractor_name"].notna() \
      & source["license_number"].notna() \
      & source["city"].notna() \
      & source["state"].notna()

    source["certification_status"] = (
        "CERTIFICATION_FAILED"
    )

    full_mask = (
        source["structural_validation_passed"]
        & source["prime_bidder_name_resolved"]
    )

    identity_gap_mask = (
        source["structural_validation_passed"]
        & ~source["prime_bidder_name_resolved"]
    )

    source.loc[
        full_mask,
        "certification_status",
    ] = "CERTIFIED"

    source.loc[
        identity_gap_mask,
        "certification_status",
    ] = (
        "CERTIFIED_BIDDER_NAME_UNRESOLVED"
    )

    source["certification_basis"] = (
        "ALTERNATE_LAYOUT_EXACT_BLOCK_RANK_"
        "LINK_STAGE2_V2"
    )

    source["identity_resolution_status"] = (
        "RESOLVED"
    )

    source.loc[
        ~source["prime_bidder_name_resolved"],
        "identity_resolution_status",
    ] = "PRIME_BIDDER_NAME_UNRESOLVED"

    duplicate_ids = int(
        source["disclosure_id"]
        .duplicated()
        .sum()
    )

    failed_rows = int(
        (
            source["certification_status"]
            == "CERTIFICATION_FAILED"
        ).sum()
    )

    if duplicate_ids:
        raise RuntimeError(
            f"Duplicate disclosure IDs: "
            f"{duplicate_ids:,}"
        )

    if failed_rows:
        raise RuntimeError(
            f"Structurally invalid rows: "
            f"{failed_rows:,}"
        )

    block_audit = (
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
            unique_subcontractor_licenses=(
                "license_number",
                "nunique",
            ),
            ready_rows=(
                "structural_validation_passed",
                "sum",
            ),
            resolved_name_rows=(
                "prime_bidder_name_resolved",
                "sum",
            ),
            first_source_page=(
                "source_page_number",
                "min",
            ),
            last_source_page=(
                "source_page_number",
                "max",
            ),
        )
    )

    block_audit["duplicate_disclosure_ids"] = (
        block_audit["disclosure_rows"]
        - block_audit["unique_disclosure_ids"]
    )

    block_audit["block_certification_status"] = (
        "CERTIFIED"
    )

    unresolved_block_mask = (
        block_audit["prime_bidder_name"]
        .isna()
        | (
            block_audit["prime_bidder_name"]
            .astype(str)
            .str.strip()
            == ""
        )
    )

    block_audit.loc[
        unresolved_block_mask,
        "block_certification_status",
    ] = (
        "CERTIFIED_BIDDER_NAME_UNRESOLVED"
    )

    block_audit["certification_basis"] = (
        "EXACT_BLOCK_COUNT_SEQUENCE_LINKED"
    )

    backup_path = create_backup(
        config.database_path,
        config.backup_directory,
        "2025_alternate_stage2_certification",
    )

    write_connection = connect_database(
        config.database_path,
        read_only=False,
    )

    ensure_target_objects_absent(
        write_connection,
        [
            CERTIFIED_TABLE,
            CERTIFICATION_AUDIT_TABLE,
        ],
    )

    write_connection.register(
        "certified_frame",
        source,
    )

    write_connection.register(
        "certification_audit_frame",
        block_audit,
    )

    certified_q = quote_identifier(
        CERTIFIED_TABLE
    )

    audit_q = quote_identifier(
        CERTIFICATION_AUDIT_TABLE
    )

    write_connection.execute(
        f"""
        CREATE TABLE {certified_q} AS

        SELECT *
        FROM certified_frame
        """
    )

    write_connection.execute(
        f"""
        CREATE TABLE {audit_q} AS

        SELECT *
        FROM certification_audit_frame
        """
    )

    inserted_rows = int(
        write_connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {certified_q}
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
        "certified_frame"
    )

    write_connection.unregister(
        "certification_audit_frame"
    )

    write_connection.close()

    fully_certified_rows = int(
        (
            source["certification_status"]
            == "CERTIFIED"
        ).sum()
    )

    unresolved_name_rows = int(
        (
            source["certification_status"]
            == (
                "CERTIFIED_BIDDER_NAME_"
                "UNRESOLVED"
            )
        ).sum()
    )

    fully_certified_blocks = int(
        (
            block_audit[
                "block_certification_status"
            ]
            == "CERTIFIED"
        ).sum()
    )

    unresolved_name_blocks = int(
        (
            block_audit[
                "block_certification_status"
            ]
            == (
                "CERTIFIED_BIDDER_NAME_"
                "UNRESOLVED"
            )
        ).sum()
    )

    log_key_value(
        logger,
        "Source rows",
        len(source),
    )

    log_key_value(
        logger,
        "Certified rows",
        fully_certified_rows,
    )

    log_key_value(
        logger,
        "Certified rows with bidder-name gap",
        unresolved_name_rows,
    )

    log_key_value(
        logger,
        "Certification failures",
        failed_rows,
    )

    log_key_value(
        logger,
        "Certified bidder blocks",
        fully_certified_blocks,
    )

    log_key_value(
        logger,
        "Bidder blocks with name gap",
        unresolved_name_blocks,
    )

    log_key_value(
        logger,
        "Duplicate disclosure IDs",
        duplicate_ids,
    )

    log_key_value(
        logger,
        "Inserted certified rows",
        inserted_rows,
    )

    log_key_value(
        logger,
        "Inserted audit blocks",
        inserted_blocks,
    )

    log_key_value(
        logger,
        "Certified table",
        CERTIFIED_TABLE,
    )

    log_key_value(
        logger,
        "Certification audit table",
        CERTIFICATION_AUDIT_TABLE,
    )

    log_key_value(
        logger,
        "Backup",
        backup_path,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    if inserted_rows != len(source):
        raise RuntimeError(
            "Certified-table row count mismatch."
        )

    if inserted_blocks != len(block_audit):
        raise RuntimeError(
            "Certification-audit block count mismatch."
        )

    logger.info("")
    logger.info(
        "ALTERNATE STAGE 2 CERTIFICATION PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
