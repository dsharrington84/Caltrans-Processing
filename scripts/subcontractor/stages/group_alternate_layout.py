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


def assign_blocks(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    grouped_frames: list[pd.DataFrame] = []

    for contract_number, contract_rows in frame.groupby(
        "contract_number",
        sort=True,
    ):
        contract_rows = (
            contract_rows
            .sort_values("page_number")
            .copy()
        )

        previous_id = (
            contract_rows[
                "candidate_bidder_id"
            ].shift()
        )

        previous_page = (
            contract_rows[
                "page_number"
            ].shift()
        )

        starts_new_block = (
            previous_id.isna()
            | (
                contract_rows[
                    "candidate_bidder_id"
                ]
                != previous_id
            )
            | (
                contract_rows[
                    "page_number"
                ]
                != previous_page + 1
            )
        )

        contract_rows[
            "bidder_block_number"
        ] = starts_new_block.cumsum()

        grouped_frames.append(
            contract_rows
        )

    return pd.concat(
        grouped_frames,
        ignore_index=True,
    )


def build_block_summary(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    summary = (
        frame.groupby(
            [
                "contract_number",
                "bidder_block_number",
            ],
            as_index=False,
        )
        .agg(
            bidder_id=(
                "candidate_bidder_id",
                "first",
            ),
            bidder_name=(
                "candidate_bidder_name",
                "first",
            ),
            first_page=(
                "page_number",
                "min",
            ),
            last_page=(
                "page_number",
                "max",
            ),
            page_count=(
                "page_number",
                "count",
            ),
            known_identity_pages=(
                "candidate_bidder_name",
                lambda values: int(
                    values.notna().sum()
                ),
            ),
            header_pages=(
                "form_header_found",
                "sum",
            ),
            total_nonempty_lines=(
                "nonempty_line_count",
                "sum",
            ),
            total_money_values=(
                "money_value_count",
                "sum",
            ),
            total_percent_values=(
                "percent_value_count",
                "sum",
            ),
        )
    )

    summary[
        "block_sequence"
    ] = (
        summary.groupby(
            "contract_number"
        ).cumcount()
        + 1
    )

    summary[
        "identity_status"
    ] = summary[
        "bidder_name"
    ].apply(
        lambda value: (
            "KNOWN"
            if pd.notna(value)
            and str(value).strip()
            else "UNKNOWN"
        )
    )

    return summary


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "group_alternate_layout",
    )

    log_section(
        logger,
        "ALTERNATE-LAYOUT BIDDER BLOCK GROUPING",
        width=160,
    )

    candidate_path = (
        config.project_root
        / "data"
        / "reports"
        / "subcontractor"
        / (
            "alternate_layout_bidder_candidates_"
            f"{config.target_year}.csv"
        )
    )

    if not candidate_path.exists():
        raise FileNotFoundError(
            "Alternate-layout candidate CSV "
            f"not found: {candidate_path}"
        )

    candidates = pd.read_csv(
        candidate_path,
        dtype={
            "contract_number": str,
            "candidate_bidder_id": str,
        },
    )

    required_columns = {
        "contract_number",
        "page_number",
        "candidate_bidder_id",
        "candidate_bidder_name",
        "form_header_found",
        "nonempty_line_count",
        "money_value_count",
        "percent_value_count",
    }

    missing_columns = sorted(
        required_columns
        - set(candidates.columns)
    )

    if missing_columns:
        raise RuntimeError(
            "Candidate CSV missing columns: "
            + ", ".join(missing_columns)
        )

    candidates[
        "page_number"
    ] = pd.to_numeric(
        candidates["page_number"],
        errors="raise",
    ).astype(int)

    grouped_pages = assign_blocks(
        candidates
    )

    block_summary = build_block_summary(
        grouped_pages
    )

    output_directory = (
        config.project_root
        / "data"
        / "reports"
        / "subcontractor"
    )

    page_output_path = (
        output_directory
        / (
            "alternate_layout_grouped_pages_"
            f"{config.target_year}.csv"
        )
    )

    block_output_path = (
        output_directory
        / (
            "alternate_layout_bidder_blocks_"
            f"{config.target_year}.csv"
        )
    )

    grouped_pages.to_csv(
        page_output_path,
        index=False,
    )

    block_summary.to_csv(
        block_output_path,
        index=False,
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

    rank_counts = connection.execute(
        f"""
        SELECT
            contract_number,
            COUNT(
                DISTINCT bid_rank
            ) AS authoritative_bid_ranks

        FROM {history_q}

        WHERE contract_number IN (
            SELECT DISTINCT
                contract_number
            FROM read_csv_auto(?)
        )
          AND bid_rank IS NOT NULL

        GROUP BY
            contract_number
        """,
        [str(block_output_path)],
    ).fetchdf()

    connection.close()

    contract_summary = (
        block_summary.groupby(
            "contract_number",
            as_index=False,
        )
        .agg(
            bidder_blocks=(
                "bidder_block_number",
                "count",
            ),
            unique_bidder_ids=(
                "bidder_id",
                "nunique",
            ),
            known_blocks=(
                "identity_status",
                lambda values: int(
                    (values == "KNOWN").sum()
                ),
            ),
            unknown_blocks=(
                "identity_status",
                lambda values: int(
                    (values == "UNKNOWN").sum()
                ),
            ),
            first_page=(
                "first_page",
                "min",
            ),
            last_page=(
                "last_page",
                "max",
            ),
            bidder_form_pages=(
                "page_count",
                "sum",
            ),
        )
        .merge(
            rank_counts,
            on="contract_number",
            how="left",
        )
    )

    contract_summary[
        "rank_difference"
    ] = (
        contract_summary[
            "bidder_blocks"
        ]
        - contract_summary[
            "authoritative_bid_ranks"
        ].fillna(0)
    ).astype(int)

    contract_summary[
        "rank_alignment"
    ] = contract_summary[
        "rank_difference"
    ].apply(
        lambda value: (
            "EXACT"
            if value == 0
            else (
                f"EXTRA_{value}"
                if value > 0
                else f"MISSING_{abs(value)}"
            )
        )
    )

    contract_output_path = (
        output_directory
        / (
            "alternate_layout_contract_reconciliation_"
            f"{config.target_year}.csv"
        )
    )

    contract_summary.to_csv(
        contract_output_path,
        index=False,
    )

    log_key_value(
        logger,
        "Candidate pages",
        len(candidates),
    )

    log_key_value(
        logger,
        "Bidder-form blocks",
        len(block_summary),
    )

    log_key_value(
        logger,
        "Contracts",
        block_summary[
            "contract_number"
        ].nunique(),
    )

    log_subsection(
        logger,
        "CONTRACT RECONCILIATION",
        width=160,
    )

    logger.info(
        "%-13s %8s %10s %10s %10s %10s %14s",
        "Contract",
        "Ranks",
        "Blocks",
        "Unique IDs",
        "Known",
        "Unknown",
        "Alignment",
    )

    logger.info("-" * 95)

    for row in contract_summary.itertuples(
        index=False,
    ):
        logger.info(
            "%-13s %8d %10d %10d %10d %10d %14s",
            row.contract_number,
            int(
                row.authoritative_bid_ranks
            ),
            int(row.bidder_blocks),
            int(row.unique_bidder_ids),
            int(row.known_blocks),
            int(row.unknown_blocks),
            row.rank_alignment,
        )

    repeated_nonconsecutive_ids = (
        block_summary.groupby(
            [
                "contract_number",
                "bidder_id",
            ]
        )
        .size()
        .reset_index(
            name="block_count"
        )
    )

    repeated_nonconsecutive_ids = (
        repeated_nonconsecutive_ids[
            repeated_nonconsecutive_ids[
                "block_count"
            ] > 1
        ]
    )

    exact_contracts = int(
        (
            contract_summary[
                "rank_alignment"
            ] == "EXACT"
        ).sum()
    )

    unknown_blocks = int(
        (
            block_summary[
                "identity_status"
            ] == "UNKNOWN"
        ).sum()
    )

    log_subsection(
        logger,
        "GROUPING SUMMARY",
        width=160,
    )

    log_key_value(
        logger,
        "Exact rank/block contracts",
        exact_contracts,
    )

    log_key_value(
        logger,
        "Contracts requiring reconciliation",
        len(contract_summary)
        - exact_contracts,
    )

    log_key_value(
        logger,
        "Unknown bidder blocks",
        unknown_blocks,
    )

    log_key_value(
        logger,
        "Nonconsecutive repeated bidder IDs",
        len(
            repeated_nonconsecutive_ids
        ),
    )

    log_key_value(
        logger,
        "Block CSV",
        block_output_path,
    )

    log_key_value(
        logger,
        "Contract reconciliation CSV",
        contract_output_path,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    logger.info("")
    logger.info(
        "ALTERNATE-LAYOUT BLOCK GROUPING PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
