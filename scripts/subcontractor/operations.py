from __future__ import annotations

import argparse
import json
from typing import Any

import duckdb

from scripts.subcontractor.framework import (
    FrameworkContext,
)


def table_exists(
    context: FrameworkContext,
    con: duckdb.DuckDBPyConnection,
    table_name: str,
) -> bool:
    return context.table_exists(
        table_name,
        connection=con,
    )


def command_stats() -> int:
    context = FrameworkContext.load()

    con = context.connect(
        read_only=True,
    )

    try:
        print()
        print("SUBCONTRACTOR DATASET STATISTICS")
        print("=" * 130)
        print(f"Database: {context.paths.database}")
        print(f"Target year: {context.target_year}")
        print(
            "Target districts: "
            + ", ".join(
                str(value)
                for value in context.target_districts
            )
        )

        datasets = (
            (
                "Current relationships",
                "bid_tab_subcontractor_relationship_current",
            ),
            (
                "Current relationships V2",
                "bid_tab_subcontractor_relationship_current_v2",
            ),
            (
                "2025 batch relationships",
                "bid_tab_subcontractor_relationship_normalized_2025_batch1_v1",
            ),
            (
                "2025 normalized V2",
                "bid_tab_subcontractor_relationship_normalized_2025_v2",
            ),
            (
                "Alternate promoted disclosures",
                "bid_tab_subcontractor_disclosure_2025_alt_promoted_v1",
            ),
            (
                "Alternate relationship candidate V2",
                "bid_tab_subcontractor_relationship_2025_alt_candidate_v2",
            ),
            (
                "Quarantine registry",
                "bid_tab_subcontractor_quarantined_2025_v1",
            ),
        )

        print()
        print("DATASETS")
        print("-" * 130)
        print(
            f"{'Dataset':<44}"
            f"{'Rows':>14}"
            f"{'Contracts':>14}"
        )

        for label, table_name in datasets:
            if not table_exists(
                context,
                con,
                table_name,
            ):
                print(
                    f"{label:<44}"
                    f"{'N/A':>14}"
                    f"{'N/A':>14}"
                )
                continue

            columns = set(
                con.execute(
                    f'DESCRIBE "{table_name}"'
                ).fetchdf()["column_name"]
                .astype(str)
                .tolist()
            )

            row_count = con.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]

            contract_count: int | str = "N/A"

            if "contract_number" in columns:
                contract_count = con.execute(
                    f"""
                    SELECT COUNT(
                        DISTINCT contract_number
                    )
                    FROM "{table_name}"
                    """
                ).fetchone()[0]

            print(
                f"{label:<44}"
                f"{row_count:>14,}"
                f"{contract_count:>14}"
            )

        current_candidates = (
            "bid_tab_subcontractor_relationship_current_v2",
            "bid_tab_subcontractor_relationship_current",
        )

        current_table = next(
            (
                table
                for table in current_candidates
                if table_exists(
                    context,
                    con,
                    table,
                )
            ),
            None,
        )

        if current_table is not None:
            print()
            print("CURRENT RELATIONSHIPS")
            print("-" * 130)
            print(f"Source table: {current_table}")
            print()

            print(
                con.execute(
                    f"""
                    SELECT
                        COUNT(*) AS relationships,

                        COUNT(
                            DISTINCT contract_number
                        ) AS contracts,

                        COUNT(
                            DISTINCT prime_bidder_id
                        ) AS prime_bidders,

                        COUNT(
                            DISTINCT subcontractor_name
                        ) AS subcontractors,

                        COUNT(*) FILTER (
                            WHERE eligible_for_prime_pricing_analysis
                        ) AS pricing_eligible,

                        COUNT(*) FILTER (
                            WHERE prime_bidder_name IS NULL
                               OR TRIM(prime_bidder_name) = ''
                        ) AS prime_identity_gaps

                    FROM "{current_table}"
                    """
                ).fetchdf().to_string(
                    index=False
                )
            )

        alternate_table = (
            "bid_tab_subcontractor_"
            "relationship_2025_alt_candidate_v2"
        )

        if table_exists(
            context,
            con,
            alternate_table,
        ):
            print()
            print("ALTERNATE CANDIDATE V2")
            print("-" * 130)

            print(
                con.execute(
                    f"""
                    SELECT
                        contract_number,

                        COUNT(*) AS relationships,

                        COUNT(
                            DISTINCT prime_bidder_id
                        ) AS prime_bidders,

                        SUM(disclosure_rows)
                            AS disclosure_rows,

                        COUNT(*) FILTER (
                            WHERE production_identity_class
                                = 'PRIME_IDENTITY_GAP'
                        ) AS identity_gap_relationships,

                        COUNT(*) FILTER (
                            WHERE eligible_for_prime_pricing_analysis
                        ) AS pricing_eligible_relationships

                    FROM "{alternate_table}"

                    GROUP BY
                        contract_number

                    ORDER BY
                        contract_number
                    """
                ).fetchdf().to_string(
                    index=False
                )
            )

        quarantine_table = (
            "bid_tab_subcontractor_quarantined_2025_v1"
        )

        if table_exists(
            context,
            con,
            quarantine_table,
        ):
            print()
            print("QUARANTINE")
            print("-" * 130)

            print(
                con.execute(
                    f"""
                    SELECT
                        quarantine_reason,
                        COUNT(*) AS contracts,
                        SUM(authoritative_rank_count)
                            AS ranked_bidders,
                        SUM(disclosure_block_count)
                            AS disclosure_blocks

                    FROM "{quarantine_table}"

                    GROUP BY
                        quarantine_reason

                    ORDER BY
                        quarantine_reason
                    """
                ).fetchdf().to_string(
                    index=False
                )
            )

    finally:
        con.close()

    return 0


def print_value(
    value: Any,
    *,
    indent: int = 0,
) -> None:
    prefix = " " * indent

    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(
                child,
                (
                    dict,
                    list,
                ),
            ):
                print(
                    f"{prefix}{key}:"
                )

                print_value(
                    child,
                    indent=indent + 2,
                )
            else:
                print(
                    f"{prefix}{key}: {child}"
                )

        return

    if isinstance(value, list):
        for child in value:
            if isinstance(
                child,
                (
                    dict,
                    list,
                ),
            ):
                print(
                    f"{prefix}-"
                )

                print_value(
                    child,
                    indent=indent + 2,
                )
            else:
                print(
                    f"{prefix}- {child}"
                )

        return

    print(
        f"{prefix}{value}"
    )


def command_config_show(
    *,
    raw_json: bool,
) -> int:
    context = FrameworkContext.load()

    print()
    print("SUBCONTRACTOR CONFIGURATION")
    print("=" * 130)
    print(f"Source: {context.paths.config}")
    print()

    if raw_json:
        print(
            json.dumps(
                context.settings,
                indent=2,
                sort_keys=True,
            )
        )

        return 0

    print_value(
        context.settings
    )

    print()
    print("RESOLVED PATHS")
    print("-" * 130)
    print(
        f"{'project_root':<18}"
        f"{context.paths.project_root}"
    )
    print(
        f"{'config':<18}"
        f"{context.paths.config}"
    )
    print(
        f"{'database':<18}"
        f"{context.paths.database}"
    )
    print(
        f"{'backups':<18}"
        f"{context.paths.backups}"
    )
    print(
        f"{'cache':<18}"
        f"{context.paths.cache}"
    )
    print(
        f"{'logs':<18}"
        f"{context.paths.logs}"
    )
    print(
        f"{'reports':<18}"
        f"{context.paths.reports}"
    )

    print()
    print("NORMALIZED SETTINGS")
    print("-" * 130)
    print(
        f"{'target_year':<18}"
        f"{context.target_year}"
    )
    print(
        f"{'target_districts':<18}"
        + ", ".join(
            str(value)
            for value in context.target_districts
        )
    )
    print(
        f"{'configured_tables':<18}"
        f"{len(context.tables)}"
    )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only operational commands for the "
            "subcontractor-processing framework."
        )
    )

    subparsers = parser.add_subparsers(
        dest="operation",
        required=True,
    )

    subparsers.add_parser(
        "stats",
        help=(
            "Show production and pipeline statistics."
        ),
    )

    config_parser = subparsers.add_parser(
        "config-show",
        help=(
            "Display configuration and resolved paths."
        ),
    )

    config_parser.add_argument(
        "--json",
        action="store_true",
        help="Print formatted raw JSON.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.operation == "stats":
        return command_stats()

    if arguments.operation == "config-show":
        return command_config_show(
            raw_json=arguments.json,
        )

    parser.error(
        f"Unsupported operation: "
        f"{arguments.operation}"
    )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
