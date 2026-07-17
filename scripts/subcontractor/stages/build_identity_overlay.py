from __future__ import annotations

import re

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
    "2025_alt_certified_v1"
)

HISTORY_TABLE = (
    "historical_bid_prices_identity_enriched_v1"
)

OVERLAY_TABLE = (
    "bid_tab_subcontractor_disclosure_"
    "2025_alt_identity_overlay_v1"
)

IDENTITY_AUDIT_TABLE = (
    "bid_tab_subcontractor_alt_"
    "identity_audit_2025_v1"
)

IDENTITY_REVIEW_TABLE = (
    "bid_tab_subcontractor_alt_"
    "identity_review_2025_v1"
)


def normalize_identifier(
    value: object,
) -> str:
    value = re.sub(
        r"[^A-Z0-9]",
        "",
        "" if value is None else str(value).upper(),
    )

    if value.startswith("VCO"):
        value = "VC0" + value[3:]

    return value


def normalize_name(
    value: object,
) -> str | None:
    if value is None:
        return None

    text = re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()

    if not text or text.lower() == "nan":
        return None

    return text


def build_history_identity_candidates(
    connection,
) -> pd.DataFrame:
    history_q = quote_identifier(
        HISTORY_TABLE
    )

    frame = connection.execute(
        f"""
        SELECT
            bidder_id,
            bidder_name,
            COUNT(
                DISTINCT contract_number
            ) AS supporting_contracts,
            COUNT(*) AS supporting_rows,
            MAX(
                CASE
                    WHEN identity_overlay_status
                        IS NOT NULL
                    THEN 1
                    ELSE 0
                END
            ) AS overlay_evidence,
            MAX(
                CASE
                    WHEN bidder_identity_status
                        IS NOT NULL
                    THEN 1
                    ELSE 0
                END
            ) AS identity_status_evidence

        FROM {history_q}

        WHERE bidder_id IS NOT NULL
          AND bidder_name IS NOT NULL
          AND TRIM(
                CAST(
                    bidder_id AS VARCHAR
                )
              ) <> ''
          AND TRIM(
                CAST(
                    bidder_name AS VARCHAR
                )
              ) <> ''

        GROUP BY
            bidder_id,
            bidder_name
        """
    ).fetchdf()

    if frame.empty:
        return frame

    frame[
        "normalized_bidder_id"
    ] = frame[
        "bidder_id"
    ].map(
        normalize_identifier
    )

    frame[
        "normalized_bidder_name"
    ] = frame[
        "bidder_name"
    ].map(
        normalize_name
    )

    frame = frame[
        frame[
            "normalized_bidder_id"
        ] != ""
    ].copy()

    frame[
        "identity_score"
    ] = (
        frame[
            "supporting_contracts"
        ].fillna(0) * 100000
        + frame[
            "supporting_rows"
        ].fillna(0) * 100
        + frame[
            "overlay_evidence"
        ].fillna(0) * 10
        + frame[
            "identity_status_evidence"
        ].fillna(0)
    )

    frame = (
        frame.sort_values(
            [
                "normalized_bidder_id",
                "identity_score",
                "normalized_bidder_name",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
        .drop_duplicates(
            subset=[
                "normalized_bidder_id",
            ],
            keep="first",
        )
    )

    return frame


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "build_identity_overlay",
    )

    log_section(
        logger,
        "ALTERNATE DISCLOSURE IDENTITY OVERLAY",
        width=160,
    )

    read_connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        read_connection,
        [
            SOURCE_TABLE,
            HISTORY_TABLE,
        ],
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

    identity_candidates = (
        build_history_identity_candidates(
            read_connection
        )
    )

    read_connection.close()

    if source.empty:
        raise RuntimeError(
            "Certified alternate disclosure "
            "table is empty."
        )

    source[
        "normalized_prime_bidder_id"
    ] = source[
        "prime_bidder_id"
    ].map(
        normalize_identifier
    )

    if identity_candidates.empty:
        identity_lookup = pd.DataFrame(
            columns=[
                "normalized_bidder_id",
                "history_bidder_name",
                "supporting_contracts",
                "supporting_rows",
                "identity_score",
            ]
        )
    else:
        identity_lookup = (
            identity_candidates[
                [
                    "normalized_bidder_id",
                    "normalized_bidder_name",
                    "supporting_contracts",
                    "supporting_rows",
                    "identity_score",
                ]
            ]
            .rename(
                columns={
                    "normalized_bidder_name": (
                        "history_bidder_name"
                    ),
                }
            )
        )

    overlay = source.merge(
        identity_lookup,
        left_on=(
            "normalized_prime_bidder_id"
        ),
        right_on=(
            "normalized_bidder_id"
        ),
        how="left",
    )

    overlay[
        "original_prime_bidder_name"
    ] = overlay[
        "prime_bidder_name"
    ].map(
        normalize_name
    )

    overlay[
        "resolved_prime_bidder_name"
    ] = overlay[
        "original_prime_bidder_name"
    ]

    history_fill_mask = (
        overlay[
            "resolved_prime_bidder_name"
        ].isna()
        & overlay[
            "history_bidder_name"
        ].notna()
    )

    overlay.loc[
        history_fill_mask,
        "resolved_prime_bidder_name",
    ] = overlay.loc[
        history_fill_mask,
        "history_bidder_name",
    ]

    overlay[
        "identity_resolution_basis"
    ] = (
        "CERTIFIED_SOURCE_NAME"
    )

    overlay.loc[
        history_fill_mask,
        "identity_resolution_basis",
    ] = (
        "GLOBAL_HISTORY_BIDDER_ID_MATCH"
    )

    unresolved_mask = overlay[
        "resolved_prime_bidder_name"
    ].isna()

    overlay.loc[
        unresolved_mask,
        "identity_resolution_basis",
    ] = (
        "UNRESOLVED_NO_AUTHORITATIVE_NAME"
    )

    overlay[
        "identity_overlay_status"
    ] = "RESOLVED"

    overlay.loc[
        unresolved_mask,
        "identity_overlay_status",
    ] = "REVIEW_REQUIRED"

    overlay[
        "promotion_status"
    ] = "READY_FOR_PROMOTION"

    overlay.loc[
        unresolved_mask,
        "promotion_status",
    ] = (
        "READY_WITH_IDENTITY_GAP"
    )

    overlay[
        "prime_bidder_name"
    ] = overlay[
        "resolved_prime_bidder_name"
    ]

    drop_columns = [
        "normalized_bidder_id",
        "history_bidder_name",
    ]

    overlay = overlay.drop(
        columns=[
            column
            for column in drop_columns
            if column in overlay.columns
        ]
    )

    identity_audit = (
        overlay.groupby(
            [
                "contract_number",
                "bid_rank",
                "prime_bidder_id",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            original_prime_bidder_name=(
                "original_prime_bidder_name",
                "first",
            ),
            resolved_prime_bidder_name=(
                "resolved_prime_bidder_name",
                "first",
            ),
            identity_resolution_basis=(
                "identity_resolution_basis",
                "first",
            ),
            identity_overlay_status=(
                "identity_overlay_status",
                "first",
            ),
            promotion_status=(
                "promotion_status",
                "first",
            ),
            supporting_contracts=(
                "supporting_contracts",
                "max",
            ),
            supporting_rows=(
                "supporting_rows",
                "max",
            ),
            disclosure_rows=(
                "disclosure_id",
                "count",
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

    identity_review = identity_audit[
        identity_audit[
            "identity_overlay_status"
        ]
        == "REVIEW_REQUIRED"
    ].copy()

    duplicate_ids = int(
        overlay[
            "disclosure_id"
        ].duplicated().sum()
    )

    source_row_count = len(
        source
    )

    overlay_row_count = len(
        overlay
    )

    if duplicate_ids:
        raise RuntimeError(
            f"Duplicate disclosure IDs found: "
            f"{duplicate_ids:,}"
        )

    if overlay_row_count != source_row_count:
        raise RuntimeError(
            "Identity overlay changed the "
            "disclosure row count."
        )

    backup_path = create_backup(
        config.database_path,
        config.backup_directory,
        "2025_alternate_identity_overlay",
    )

    write_connection = connect_database(
        config.database_path,
        read_only=False,
    )

    ensure_target_objects_absent(
        write_connection,
        [
            OVERLAY_TABLE,
            IDENTITY_AUDIT_TABLE,
            IDENTITY_REVIEW_TABLE,
        ],
    )

    write_connection.register(
        "identity_overlay_frame",
        overlay,
    )

    write_connection.register(
        "identity_audit_frame",
        identity_audit,
    )

    write_connection.register(
        "identity_review_frame",
        identity_review,
    )

    overlay_q = quote_identifier(
        OVERLAY_TABLE
    )

    audit_q = quote_identifier(
        IDENTITY_AUDIT_TABLE
    )

    review_q = quote_identifier(
        IDENTITY_REVIEW_TABLE
    )

    write_connection.execute(
        f"""
        CREATE TABLE {overlay_q} AS

        SELECT *
        FROM identity_overlay_frame
        """
    )

    write_connection.execute(
        f"""
        CREATE TABLE {audit_q} AS

        SELECT *
        FROM identity_audit_frame
        """
    )

    write_connection.execute(
        f"""
        CREATE TABLE {review_q} AS

        SELECT *
        FROM identity_review_frame
        """
    )

    inserted_overlay_rows = int(
        write_connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {overlay_q}
            """
        ).fetchone()[0]
    )

    inserted_audit_rows = int(
        write_connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {audit_q}
            """
        ).fetchone()[0]
    )

    inserted_review_rows = int(
        write_connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {review_q}
            """
        ).fetchone()[0]
    )

    write_connection.unregister(
        "identity_overlay_frame"
    )

    write_connection.unregister(
        "identity_audit_frame"
    )

    write_connection.unregister(
        "identity_review_frame"
    )

    write_connection.close()

    resolved_blocks = int(
        (
            identity_audit[
                "identity_overlay_status"
            ]
            == "RESOLVED"
        ).sum()
    )

    unresolved_blocks = int(
        (
            identity_audit[
                "identity_overlay_status"
            ]
            == "REVIEW_REQUIRED"
        ).sum()
    )

    resolved_rows = int(
        (
            overlay[
                "identity_overlay_status"
            ]
            == "RESOLVED"
        ).sum()
    )

    unresolved_rows = int(
        (
            overlay[
                "identity_overlay_status"
            ]
            == "REVIEW_REQUIRED"
        ).sum()
    )

    log_key_value(
        logger,
        "Source disclosure rows",
        source_row_count,
    )

    log_key_value(
        logger,
        "Overlay disclosure rows",
        inserted_overlay_rows,
    )

    log_key_value(
        logger,
        "Resolved bidder blocks",
        resolved_blocks,
    )

    log_key_value(
        logger,
        "Unresolved bidder blocks",
        unresolved_blocks,
    )

    log_key_value(
        logger,
        "Resolved disclosure rows",
        resolved_rows,
    )

    log_key_value(
        logger,
        "Rows retaining identity gap",
        unresolved_rows,
    )

    log_key_value(
        logger,
        "Duplicate disclosure IDs",
        duplicate_ids,
    )

    log_key_value(
        logger,
        "Identity audit rows",
        inserted_audit_rows,
    )

    log_key_value(
        logger,
        "Identity review rows",
        inserted_review_rows,
    )

    log_key_value(
        logger,
        "Overlay table",
        OVERLAY_TABLE,
    )

    log_key_value(
        logger,
        "Identity audit table",
        IDENTITY_AUDIT_TABLE,
    )

    log_key_value(
        logger,
        "Identity review table",
        IDENTITY_REVIEW_TABLE,
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

    log_subsection(
        logger,
        "UNRESOLVED PRIME BIDDER IDENTITIES",
        width=160,
    )

    if identity_review.empty:
        logger.info(
            "No unresolved identities remain."
        )
    else:
        logger.info(
            "%-13s %6s %-14s %8s %8s %s",
            "Contract",
            "Rank",
            "Bidder ID",
            "Rows",
            "Pages",
            "Resolution basis",
        )

        logger.info("-" * 105)

        for row in identity_review.itertuples(
            index=False,
        ):
            page_range = (
                f"{int(row.first_source_page)}-"
                f"{int(row.last_source_page)}"
            )

            logger.info(
                "%-13s %6d %-14s %8d %8s %s",
                row.contract_number,
                int(row.bid_rank),
                row.prime_bidder_id,
                int(row.disclosure_rows),
                page_range,
                row.identity_resolution_basis,
            )

    logger.info("")
    logger.info(
        "ALTERNATE IDENTITY OVERLAY PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
