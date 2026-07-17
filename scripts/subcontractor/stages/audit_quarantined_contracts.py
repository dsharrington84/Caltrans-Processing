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

RAW_PAGE_TABLE = (
    "bid_tab_subcontractor_raw_page_text_"
    "2025_incremental_v1"
)


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "audit_quarantined_contracts",
    )

    log_section(
        logger,
        "QUARANTINED CONTRACT RECONCILIATION AUDIT",
        width=170,
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
            f"Contract reconciliation not found: "
            f"{contract_path}"
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

    quarantined = contracts[
        contracts["rank_alignment"]
        != "EXACT"
    ].copy()

    quarantined_contracts = (
        quarantined[
            "contract_number"
        ]
        .drop_duplicates()
        .tolist()
    )

    if not quarantined_contracts:
        logger.info(
            "No quarantined contracts remain."
        )
        return 0

    blocks = blocks[
        blocks["contract_number"].isin(
            quarantined_contracts
        )
    ].copy()

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        connection,
        [
            HISTORY_TABLE,
            RAW_PAGE_TABLE,
        ],
    )

    history_q = quote_identifier(
        HISTORY_TABLE
    )

    raw_q = quote_identifier(
        RAW_PAGE_TABLE
    )

    placeholders = ", ".join(
        ["?"] * len(
            quarantined_contracts
        )
    )

    history = connection.execute(
        f"""
        SELECT
            contract_number,
            bid_rank,
            MAX(bidder_id)
                AS bidder_id,
            MAX(bidder_name)
                AS bidder_name,
            MAX(certified_bid_total)
                AS certified_bid_total,
            MAX(is_winning_bid)
                AS is_winning_bid,
            MAX(
                identity_resolution_basis
            ) AS identity_resolution_basis,
            MAX(
                bidder_identity_status
            ) AS bidder_identity_status

        FROM {history_q}

        WHERE contract_number IN (
            {placeholders}
        )
          AND bid_rank IS NOT NULL

        GROUP BY
            contract_number,
            bid_rank

        ORDER BY
            contract_number,
            bid_rank
        """,
        quarantined_contracts,
    ).fetchdf()

    raw_page_ranges = connection.execute(
        f"""
        SELECT
            contract_number,
            MIN(page_number)
                AS first_raw_page,
            MAX(page_number)
                AS last_raw_page,
            COUNT(*)
                AS raw_pages

        FROM {raw_q}

        WHERE contract_number IN (
            {placeholders}
        )

        GROUP BY
            contract_number
        """,
        quarantined_contracts,
    ).fetchdf()

    connection.close()

    block_rows: list[dict] = []

    for contract_number, contract_blocks in (
        blocks.groupby(
            "contract_number",
            sort=True,
        )
    ):
        contract_blocks = (
            contract_blocks
            .sort_values(
                "block_sequence"
            )
            .copy()
        )

        previous_last_page = None

        for row in contract_blocks.itertuples(
            index=False,
        ):
            if previous_last_page is None:
                gap_before = None
            else:
                gap_before = (
                    int(row.first_page)
                    - int(previous_last_page)
                    - 1
                )

            block_rows.append(
                {
                    "contract_number": (
                        contract_number
                    ),
                    "block_sequence": int(
                        row.block_sequence
                    ),
                    "bidder_id": (
                        row.bidder_id
                    ),
                    "bidder_name": (
                        row.bidder_name
                    ),
                    "first_page": int(
                        row.first_page
                    ),
                    "last_page": int(
                        row.last_page
                    ),
                    "page_count": int(
                        row.page_count
                    ),
                    "gap_before_block": (
                        gap_before
                    ),
                    "identity_status": (
                        row.identity_status
                    ),
                }
            )

            previous_last_page = int(
                row.last_page
            )

    block_audit = pd.DataFrame(
        block_rows
    )

    contract_audit = (
        quarantined.merge(
            raw_page_ranges,
            on="contract_number",
            how="left",
        )
    )

    contract_audit[
        "likely_reconciliation_case"
    ] = contract_audit[
        "rank_alignment"
    ].apply(
        lambda value: (
            "POSSIBLE_UNRANKED_OR_INELIGIBLE_BLOCK"
            if str(value).startswith(
                "EXTRA_"
            )
            else (
                "POSSIBLE_NO_DISCLOSURE_BIDDER"
                if str(value).startswith(
                    "MISSING_"
                )
                else "UNKNOWN"
            )
        )
    )

    block_output = (
        report_directory
        / (
            "quarantined_bidder_block_audit_"
            f"{config.target_year}.csv"
        )
    )

    rank_output = (
        report_directory
        / (
            "quarantined_authoritative_rank_audit_"
            f"{config.target_year}.csv"
        )
    )

    contract_output = (
        report_directory
        / (
            "quarantined_contract_case_audit_"
            f"{config.target_year}.csv"
        )
    )

    block_audit.to_csv(
        block_output,
        index=False,
    )

    history.to_csv(
        rank_output,
        index=False,
    )

    contract_audit.to_csv(
        contract_output,
        index=False,
    )

    log_key_value(
        logger,
        "Quarantined contracts",
        len(quarantined_contracts),
    )

    log_key_value(
        logger,
        "Quarantined bidder blocks",
        len(block_audit),
    )

    log_key_value(
        logger,
        "Authoritative ranked bidders",
        len(history),
    )

    log_subsection(
        logger,
        "CONTRACT CASES",
        width=170,
    )

    logger.info(
        "%-13s %8s %8s %14s %-42s",
        "Contract",
        "Ranks",
        "Blocks",
        "Alignment",
        "Likely case",
    )

    logger.info("-" * 95)

    for row in contract_audit.itertuples(
        index=False,
    ):
        logger.info(
            "%-13s %8d %8d %14s %-42s",
            row.contract_number,
            int(
                row.authoritative_bid_ranks
            ),
            int(row.bidder_blocks),
            row.rank_alignment,
            row.likely_reconciliation_case,
        )

    log_subsection(
        logger,
        "BIDDER BLOCKS",
        width=170,
    )

    logger.info(
        "%-13s %5s %-14s %-42s %7s %7s %7s %s",
        "Contract",
        "Seq",
        "Bidder ID",
        "Known bidder name",
        "First",
        "Last",
        "Gap",
        "Identity",
    )

    logger.info("-" * 130)

    for row in block_audit.itertuples(
        index=False,
    ):
        bidder_name = (
            ""
            if pd.isna(
                row.bidder_name
            )
            else str(row.bidder_name)
        )

        gap_value = (
            "-"
            if pd.isna(
                row.gap_before_block
            )
            else str(
                int(row.gap_before_block)
            )
        )

        logger.info(
            "%-13s %5d %-14s %-42s %7d %7d %7s %s",
            row.contract_number,
            int(row.block_sequence),
            row.bidder_id,
            bidder_name[:42],
            int(row.first_page),
            int(row.last_page),
            gap_value,
            row.identity_status,
        )

    log_subsection(
        logger,
        "AUTHORITATIVE RANKS",
        width=170,
    )

    logger.info(
        "%-13s %6s %-14s %-42s %14s %10s",
        "Contract",
        "Rank",
        "Bidder ID",
        "Bidder name",
        "Certified total",
        "Winner",
    )

    logger.info("-" * 115)

    for row in history.itertuples(
        index=False,
    ):
        bidder_id = (
            ""
            if pd.isna(
                row.bidder_id
            )
            else str(row.bidder_id)
        )

        bidder_name = (
            ""
            if pd.isna(
                row.bidder_name
            )
            else str(row.bidder_name)
        )

        certified_total = (
            "-"
            if pd.isna(
                row.certified_bid_total
            )
            else f"{float(row.certified_bid_total):,.2f}"
        )

        winner = (
            "-"
            if pd.isna(
                row.is_winning_bid
            )
            else str(
                bool(row.is_winning_bid)
            )
        )

        logger.info(
            "%-13s %6d %-14s %-42s %14s %10s",
            row.contract_number,
            int(row.bid_rank),
            bidder_id,
            bidder_name[:42],
            certified_total,
            winner,
        )

    extra_contracts = int(
        contract_audit[
            "rank_alignment"
        ].astype(str).str.startswith(
            "EXTRA_"
        ).sum()
    )

    missing_contracts = int(
        contract_audit[
            "rank_alignment"
        ].astype(str).str.startswith(
            "MISSING_"
        ).sum()
    )

    log_subsection(
        logger,
        "AUDIT SUMMARY",
        width=170,
    )

    log_key_value(
        logger,
        "Extra-block contracts",
        extra_contracts,
    )

    log_key_value(
        logger,
        "Missing-block contracts",
        missing_contracts,
    )

    log_key_value(
        logger,
        "Block audit CSV",
        block_output,
    )

    log_key_value(
        logger,
        "Rank audit CSV",
        rank_output,
    )

    log_key_value(
        logger,
        "Contract case CSV",
        contract_output,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    logger.info("")
    logger.info(
        "QUARANTINED CONTRACT AUDIT PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
