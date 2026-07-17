from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import duckdb

from scripts.subcontractor.backup_service import (
    format_backup_result,
)
from scripts.subcontractor.framework import (
    FrameworkContext,
)


def format_bytes(
    value: int,
) -> str:
    amount = float(value)

    for unit in (
        "B",
        "KB",
        "MB",
        "GB",
        "TB",
    ):
        if amount < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(amount):,} {unit}"

            return f"{amount:,.1f} {unit}"

        amount /= 1024

    return f"{value:,} B"


def collect_files(
    directory: Path,
    pattern: str,
    limit: int,
) -> list[Path]:
    if not directory.exists():
        return []

    files = [
        path
        for path in directory.glob(pattern)
        if path.is_file()
    ]

    files.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    return files[:limit]


def print_files(
    title: str,
    files: list[Path],
) -> None:
    print()
    print(title)
    print("-" * 130)

    if not files:
        print("No files found.")
        return

    print(
        f"{'Modified':<24}"
        f"{'Size':>12}  "
        f"Name"
    )

    for path in files:
        modified = datetime.fromtimestamp(
            path.stat().st_mtime
        ).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        print(
            f"{modified:<24}"
            f"{format_bytes(path.stat().st_size):>12}  "
            f"{path.name}"
        )


def command_backup(
    *,
    reason: str,
    verify_checksum: bool,
) -> int:
    context = FrameworkContext.load()

    print()
    print("DATABASE BACKUP")
    print("=" * 130)
    print(f"Source: {context.paths.database}")
    print(f"Reason: {reason}")
    print()

    result = context.create_backup(
        reason,
        verify_checksum=verify_checksum,
    )

    print(
        format_backup_result(result)
    )

    print()
    print("BACKUP VALIDATED")

    return 0


def command_logs(
    *,
    limit: int,
) -> int:
    context = FrameworkContext.load()

    print()
    print("SUBCONTRACTOR GENERATED OUTPUTS")
    print("=" * 130)

    print_files(
        "LATEST LOGS",
        collect_files(
            context.paths.logs,
            "*.log",
            limit,
        ),
    )

    print_files(
        "LATEST REPORTS",
        collect_files(
            context.paths.reports,
            "*",
            limit,
        ),
    )

    print_files(
        "LATEST DATABASE BACKUPS",
        collect_files(
            context.paths.backups,
            "*.duckdb",
            limit,
        ),
    )

    return 0


def table_exists(
    context: FrameworkContext,
    con: duckdb.DuckDBPyConnection,
    table_name: str,
) -> bool:
    return context.table_exists(
        table_name,
        connection=con,
    )


def command_report() -> int:
    context = FrameworkContext.load()

    con = context.connect(
        read_only=True,
    )

    try:
        print()
        print("SUBCONTRACTOR PIPELINE REPORT")
        print("=" * 150)

        print()
        print("FRAMEWORK")
        print("-" * 150)
        print(f"Project: {context.paths.project_root}")
        print(f"Configuration: {context.paths.config}")
        print(f"Target year: {context.target_year}")
        print(
            "Target districts: "
            + ", ".join(
                str(value)
                for value in context.target_districts
            )
        )

        print()
        print("DATABASE")
        print("-" * 150)
        print(f"Path: {context.paths.database}")
        print(
            "Size: "
            f"{format_bytes(context.paths.database.stat().st_size)}"
        )

        table_count = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            """
        ).fetchone()[0]

        view_count = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.views
            """
        ).fetchone()[0]

        print(f"Tables: {table_count:,}")
        print(f"Views: {view_count:,}")

        datasets = (
            (
                "2024 normalized relationships",
                "bid_tab_subcontractor_relationship_normalized_2024_v2",
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
                "Alternate candidate V2",
                "bid_tab_subcontractor_relationship_2025_alt_candidate_v2",
            ),
            (
                "Quarantine registry",
                "bid_tab_subcontractor_quarantined_2025_v1",
            ),
            (
                "Current relationships",
                "bid_tab_subcontractor_relationship_current",
            ),
            (
                "Current relationships V2",
                "bid_tab_subcontractor_relationship_current_v2",
            ),
        )

        print()
        print("DATASET COVERAGE")
        print("-" * 150)
        print(
            f"{'Dataset':<46}"
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
                    f"{label:<46}"
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
                f"{label:<46}"
                f"{row_count:>14,}"
                f"{contract_count:>14}"
            )

        alt_table = (
            "bid_tab_subcontractor_"
            "relationship_2025_alt_candidate_v2"
        )

        if table_exists(
            context,
            con,
            alt_table,
        ):
            print()
            print("ALTERNATE RELATIONSHIP CANDIDATE")
            print("-" * 150)

            print(
                con.execute(
                    f"""
                    SELECT
                        contract_number,
                        COUNT(*) AS relationships,
                        COUNT(DISTINCT prime_bidder_id)
                            AS prime_bidders,
                        SUM(disclosure_rows)
                            AS disclosures,
                        COUNT(*) FILTER (
                            WHERE production_identity_class
                                = 'PRIME_IDENTITY_GAP'
                        ) AS identity_gaps,
                        COUNT(*) FILTER (
                            WHERE eligible_for_prime_pricing_analysis
                        ) AS pricing_eligible

                    FROM "{alt_table}"

                    GROUP BY
                        contract_number

                    ORDER BY
                        contract_number
                    """
                ).fetchdf().to_string(
                    index=False
                )
            )

        promotion_audit_table = (
            "bid_tab_subcontractor_"
            "alt_promotion_audit_2025_v1"
        )

        if table_exists(
            context,
            con,
            promotion_audit_table,
        ):
            print()
            print("ALTERNATE PROMOTION AUDIT")
            print("-" * 150)

            print(
                con.execute(
                    f"""
                    SELECT
                        promotion_audit_status,
                        promoted_record_status,
                        COUNT(*) AS bidder_blocks,
                        SUM(disclosure_rows)
                            AS disclosures,
                        SUM(duplicate_disclosure_ids)
                            AS duplicate_disclosure_ids

                    FROM "{promotion_audit_table}"

                    GROUP BY
                        promotion_audit_status,
                        promoted_record_status

                    ORDER BY
                        promotion_audit_status,
                        promoted_record_status
                    """
                ).fetchdf().to_string(
                    index=False
                )
            )

        quarantine_table = (
            "bid_tab_subcontractor_"
            "quarantined_2025_v1"
        )

        if table_exists(
            context,
            con,
            quarantine_table,
        ):
            print()
            print("QUARANTINE")
            print("-" * 150)

            print(
                con.execute(
                    f"""
                    SELECT
                        contract_number,
                        authoritative_rank_count,
                        disclosure_block_count,
                        quarantine_reason,
                        resolution_status

                    FROM "{quarantine_table}"

                    ORDER BY
                        contract_number
                    """
                ).fetchdf().to_string(
                    index=False
                )
            )

        print()
        print("LATEST GENERATED OUTPUTS")
        print("-" * 150)

        latest_backup = collect_files(
            context.paths.backups,
            "*.duckdb",
            1,
        )

        latest_log = collect_files(
            context.paths.logs,
            "*.log",
            1,
        )

        latest_report = collect_files(
            context.paths.reports,
            "*",
            1,
        )

        print(
            "Backup: "
            + (
                latest_backup[0].name
                if latest_backup
                else "None"
            )
        )

        print(
            "Log: "
            + (
                latest_log[0].name
                if latest_log
                else "None"
            )
        )

        print(
            "Report: "
            + (
                latest_report[0].name
                if latest_report
                else "None"
            )
        )

    finally:
        con.close()

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Maintenance commands for the "
            "subcontractor-processing framework."
        )
    )

    subparsers = parser.add_subparsers(
        dest="operation",
        required=True,
    )

    backup_parser = subparsers.add_parser(
        "backup",
        help=(
            "Create and validate a database backup."
        ),
    )

    backup_parser.add_argument(
        "--reason",
        default="manual",
        help=(
            "Short reason included in "
            "the backup filename."
        ),
    )

    backup_parser.add_argument(
        "--checksum",
        action="store_true",
        help=(
            "Validate source and backup "
            "using SHA256."
        ),
    )

    logs_parser = subparsers.add_parser(
        "logs",
        help=(
            "List recent logs, reports, and backups."
        ),
    )

    logs_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "Maximum files shown in each category."
        ),
    )

    subparsers.add_parser(
        "report",
        help=(
            "Show the consolidated pipeline report."
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.operation == "backup":
        return command_backup(
            reason=arguments.reason,
            verify_checksum=arguments.checksum,
        )

    if arguments.operation == "logs":
        return command_logs(
            limit=arguments.limit,
        )

    if arguments.operation == "report":
        return command_report()

    parser.error(
        f"Unsupported operation: "
        f"{arguments.operation}"
    )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
