from __future__ import annotations

import pandas as pd

from scripts.subcontractor.config import PipelineConfig
from scripts.subcontractor.database import (
    connect_database,
    quote_identifier,
    require_objects,
)
from scripts.subcontractor.logging_utils import (
    configure_logging,
    log_key_value,
    log_section,
    log_subsection,
)


HISTORY_TABLE = (
    "historical_bid_prices_identity_enriched_v1"
)


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "reconcile_alternate_blocks",
    )

    log_section(
        logger,
        "ALTERNATE-LAYOUT BIDDER-BLOCK RECONCILIATION",
        width=160,
    )

    report_directory = (
        config.project_root
        / "data"
        / "reports"
        / "subcontractor"
    )

    block_path = (
        report_directory
        / (
            "alternate_layout_bidder_blocks_"
            f"{config.target_year}.csv"
        )
    )

    contract_path = (
        report_directory
        / (
            "alternate_layout_contract_reconciliation_"
            f"{config.target_year}.csv"
        )
    )

    if not block_path.exists():
        raise FileNotFoundError(
            f"Block report not found: {block_path}"
        )

    if not contract_path.exists():
        raise FileNotFoundError(
            f"Contract reconciliation not found: {contract_path}"
        )

    blocks = pd.read_csv(
        block_path,
        dtype={
            "contract_number": str,
            "bidder_id": str,
        },
    )

    contracts = pd.read_csv(
        contract_path,
        dtype={
            "contract_number": str,
        },
    )

    required_block_columns = {
        "contract_number",
        "block_sequence",
        "bidder_id",
        "bidder_name",
        "first_page",
        "last_page",
        "page_count",
        "identity_status",
    }

    missing_block_columns = sorted(
        required_block_columns
        - set(blocks.columns)
    )

    if missing_block_columns:
        raise RuntimeError(
            "Block CSV missing required columns: "
            + ", ".join(missing_block_columns)
        )

    required_contract_columns = {
        "contract_number",
        "authoritative_bid_ranks",
        "bidder_blocks",
        "rank_alignment",
    }

    missing_contract_columns = sorted(
        required_contract_columns
        - set(contracts.columns)
    )

    if missing_contract_columns:
        raise RuntimeError(
            "Contract reconciliation CSV missing columns: "
            + ", ".join(missing_contract_columns)
        )

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        connection,
        [HISTORY_TABLE],
    )

    history_q = quote_identifier(
        HISTORY_TABLE
    )

    history = connection.execute(
        f"""
        SELECT
            contract_number,
            bid_rank,
            MAX(certified_bid_total)
                AS certified_bid_total,
            MAX(is_winning_bid)
                AS is_winning_bid

        FROM {history_q}

        WHERE contract_number IN (
            SELECT DISTINCT
                contract_number
            FROM read_csv_auto(?)
        )
          AND bid_rank IS NOT NULL

        GROUP BY
            contract_number,
            bid_rank

        ORDER BY
            contract_number,
            bid_rank
        """,
        [str(block_path)],
    ).fetchdf()

    connection.close()

    history[
        "bid_rank"
    ] = pd.to_numeric(
        history["bid_rank"],
        errors="raise",
    ).astype(int)

    exact_contracts = set(
        contracts.loc[
            contracts["rank_alignment"] == "EXACT",
            "contract_number",
        ]
    )

    blocks[
        "provisional_bid_rank"
    ] = pd.NA

    blocks[
        "rank_link_status"
    ] = "QUARANTINED_RECONCILIATION_REQUIRED"

    exact_mask = blocks[
        "contract_number"
    ].isin(exact_contracts)

    blocks.loc[
        exact_mask,
        "provisional_bid_rank",
    ] = blocks.loc[
        exact_mask,
        "block_sequence",
    ]

    blocks.loc[
        exact_mask,
        "rank_link_status",
    ] = "SEQUENCE_LINKED_EXACT_COUNT"

    linked = blocks.merge(
        history,
        left_on=[
            "contract_number",
            "provisional_bid_rank",
        ],
        right_on=[
            "contract_number",
            "bid_rank",
        ],
        how="left",
    )

    linked[
        "rank_history_match"
    ] = (
        linked["rank_link_status"]
        == "SEQUENCE_LINKED_EXACT_COUNT"
    ) & linked["bid_rank"].notna()

    linked[
        "certification_status"
    ] = "QUARANTINED"

    linked.loc[
        linked["rank_history_match"],
        "certification_status",
    ] = "READY_FOR_ALTERNATE_PARSE"

    exception_contracts = contracts[
        contracts[
            "rank_alignment"
        ] != "EXACT"
    ].copy()

    exception_blocks = linked[
        linked["contract_number"].isin(
            exception_contracts[
                "contract_number"
            ]
        )
    ].copy()

    linked_output = (
        report_directory
        / (
            "alternate_layout_rank_linkage_"
            f"{config.target_year}.csv"
        )
    )

    exception_output = (
        report_directory
        / (
            "alternate_layout_reconciliation_exceptions_"
            f"{config.target_year}.csv"
        )
    )

    linked.to_csv(
        linked_output,
        index=False,
    )

    exception_blocks.to_csv(
        exception_output,
        index=False,
    )

    log_key_value(
        logger,
        "Total bidder blocks",
        len(linked),
    )

    log_key_value(
        logger,
        "Exact-count contracts",
        len(exact_contracts),
    )

    log_key_value(
        logger,
        "Sequence-linked blocks",
        int(
            (
                linked["rank_link_status"]
                == "SEQUENCE_LINKED_EXACT_COUNT"
            ).sum()
        ),
    )

    log_key_value(
        logger,
        "Quarantined contracts",
        len(exception_contracts),
    )

    log_key_value(
        logger,
        "Quarantined blocks",
        len(exception_blocks),
    )

    log_subsection(
        logger,
        "EXACT CONTRACTS",
        width=160,
    )

    exact_summary = linked[
        linked[
            "rank_link_status"
        ] == "SEQUENCE_LINKED_EXACT_COUNT"
    ]

    logger.info(
        "%-13s %6s %-14s %-42s %8s %8s %s",
        "Contract",
        "Rank",
        "Bidder ID",
        "Bidder name",
        "First",
        "Last",
        "Status",
    )
    logger.info("-" * 135)

    for row in exact_summary.itertuples(
        index=False,
    ):
        logger.info(
            "%-13s %6d %-14s %-42s %8d %8d %s",
            row.contract_number,
            int(row.provisional_bid_rank),
            row.bidder_id,
            str(row.bidder_name)[:42],
            int(row.first_page),
            int(row.last_page),
            row.certification_status,
        )

    log_subsection(
        logger,
        "QUARANTINED CONTRACTS",
        width=160,
    )

    logger.info(
        "%-13s %8s %8s %14s",
        "Contract",
        "Ranks",
        "Blocks",
        "Alignment",
    )
    logger.info("-" * 55)

    for row in exception_contracts.itertuples(
        index=False,
    ):
        logger.info(
            "%-13s %8d %8d %14s",
            row.contract_number,
            int(row.authoritative_bid_ranks),
            int(row.bidder_blocks),
            row.rank_alignment,
        )

    linked_matches = int(
        exact_summary[
            "rank_history_match"
        ].sum()
    )

    expected_linked = len(
        exact_summary
    )

    log_subsection(
        logger,
        "RECONCILIATION SUMMARY",
        width=160,
    )

    log_key_value(
        logger,
        "Expected exact-linked blocks",
        expected_linked,
    )

    log_key_value(
        logger,
        "History rank matches",
        linked_matches,
    )

    log_key_value(
        logger,
        "Rank-linkage CSV",
        linked_output,
    )

    log_key_value(
        logger,
        "Exception CSV",
        exception_output,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    if linked_matches != expected_linked:
        logger.info("")
        logger.info(
            "ALTERNATE-LAYOUT RECONCILIATION FAILED"
        )
        return 1

    logger.info("")
    logger.info(
        "ALTERNATE-LAYOUT RECONCILIATION PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
