from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = (
    PROJECT_ROOT
    / "config/subcontractor/settings.json"
)

DEFAULT_DATABASE = (
    PROJECT_ROOT
    / "data/database/caltrans_pricing.duckdb"
)

DEFAULT_BACKUPS = (
    PROJECT_ROOT
    / "data/database/backups"
)

DEFAULT_LOGS = (
    PROJECT_ROOT
    / "data/logs/subcontractor"
)

DEFAULT_REPORTS = (
    PROJECT_ROOT
    / "data/reports/subcontractor"
)


def load_settings() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        settings = json.load(file)

    if not isinstance(settings, dict):
        raise TypeError(
            "Configuration must contain a JSON object."
        )

    return settings


def resolve_path(
    value: Any,
    default: Path,
) -> Path:
    if value in {
        None,
        "",
    }:
        return default.resolve()

    path = Path(
        str(value)
    ).expanduser()

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def configured_paths() -> dict[str, Path]:
    settings = load_settings()

    return {
        "database": resolve_path(
            settings.get(
                "database_path"
            ),
            DEFAULT_DATABASE,
        ),
        "backups": resolve_path(
            settings.get(
                "backup_directory"
            ),
            DEFAULT_BACKUPS,
        ),
        "logs": resolve_path(
            settings.get(
                "log_directory"
            ),
            DEFAULT_LOGS,
        ),
        "reports": resolve_path(
            settings.get(
                "report_directory"
            ),
            DEFAULT_REPORTS,
        ),
    }


def safe_slug(
    value: str,
) -> str:
    cleaned = "".join(
        character.lower()
        if character.isalnum()
        else "_"
        for character in value.strip()
    )

    cleaned = "_".join(
        part
        for part in cleaned.split("_")
        if part
    )

    return cleaned or "manual"


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


def checksum(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


def validate_duckdb(
    path: Path,
) -> tuple[int, int]:
    con = duckdb.connect(
        str(path),
        read_only=True,
    )

    try:
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

        return (
            table_count,
            view_count,
        )

    finally:
        con.close()


def command_backup(
    reason: str,
    verify_checksum: bool,
) -> int:
    paths = configured_paths()

    database = paths["database"]
    backup_directory = paths["backups"]

    if not database.exists():
        raise FileNotFoundError(
            f"Database not found: {database}"
        )

    if database.stat().st_size == 0:
        raise RuntimeError(
            "Database is zero bytes."
        )

    backup_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    reason_slug = safe_slug(
        reason
    )

    destination = (
        backup_directory
        / (
            "caltrans_pricing_"
            f"{reason_slug}_"
            f"{timestamp}.duckdb"
        )
    )

    print()
    print("DATABASE BACKUP")
    print("=" * 120)
    print(f"Source: {database}")
    print(f"Reason: {reason}")
    print(f"Destination: {destination}")
    print()

    source_tables, source_views = validate_duckdb(
        database
    )

    shutil.copy2(
        database,
        destination,
    )

    if not destination.exists():
        raise RuntimeError(
            "Backup file was not created."
        )

    source_size = database.stat().st_size
    destination_size = destination.stat().st_size

    if source_size != destination_size:
        raise RuntimeError(
            "Backup size does not match source."
        )

    backup_tables, backup_views = validate_duckdb(
        destination
    )

    if (
        backup_tables != source_tables
        or backup_views != source_views
    ):
        raise RuntimeError(
            "Backup database object counts "
            "do not match the source."
        )

    source_checksum = None
    destination_checksum = None

    if verify_checksum:
        source_checksum = checksum(
            database
        )

        destination_checksum = checksum(
            destination
        )

        if source_checksum != destination_checksum:
            raise RuntimeError(
                "Backup checksum validation failed."
            )

    print(f"Size: {format_bytes(destination_size)}")
    print(f"Tables: {backup_tables:,}")
    print(f"Views: {backup_views:,}")

    if destination_checksum is not None:
        print(
            f"SHA256: {destination_checksum}"
        )

    print()
    print("BACKUP VALIDATED")

    return 0


def collect_files(
    directory: Path,
    pattern: str,
    limit: int,
) -> list[Path]:
    if not directory.exists():
        return []

    files = [
        path
        for path in directory.glob(
            pattern
        )
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
    print("-" * 120)

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


def command_logs(
    limit: int,
) -> int:
    paths = configured_paths()

    print()
    print("SUBCONTRACTOR GENERATED OUTPUTS")
    print("=" * 120)

    print_files(
        "LATEST LOGS",
        collect_files(
            paths["logs"],
            "*.log",
            limit,
        ),
    )

    print_files(
        "LATEST REPORTS",
        collect_files(
            paths["reports"],
            "*",
            limit,
        ),
    )

    print_files(
        "LATEST DATABASE BACKUPS",
        collect_files(
            paths["backups"],
            "*.duckdb",
            limit,
        ),
    )

    return 0


def table_exists(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
) -> bool:
    return bool(
        con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = ?
            """,
            [table_name],
        ).fetchone()[0]
    )


def command_report() -> int:
    paths = configured_paths()
    database = paths["database"]

    if not database.exists():
        raise FileNotFoundError(
            f"Database not found: {database}"
        )

    con = duckdb.connect(
        str(database),
        read_only=True,
    )

    try:
        print()
        print("SUBCONTRACTOR PIPELINE REPORT")
        print("=" * 140)

        print()
        print("DATABASE")
        print("-" * 140)
        print(f"Path: {database}")
        print(f"Size: {format_bytes(database.stat().st_size)}")

        table_count = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            """
        ).fetchone()[0]

        print(f"Tables: {table_count:,}")

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
        )

        print()
        print("DATASET COVERAGE")
        print("-" * 140)
        print(
            f"{'Dataset':<44}"
            f"{'Rows':>12}"
            f"{'Contracts':>14}"
        )

        for label, table in datasets:
            if not table_exists(
                con,
                table,
            ):
                print(
                    f"{label:<44}"
                    f"{'N/A':>12}"
                    f"{'N/A':>14}"
                )
                continue

            columns = set(
                con.execute(
                    f'DESCRIBE "{table}"'
                ).fetchdf()["column_name"]
                .astype(str)
            )

            rows = con.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]

            contracts: int | str = "N/A"

            if "contract_number" in columns:
                contracts = con.execute(
                    f"""
                    SELECT COUNT(
                        DISTINCT contract_number
                    )
                    FROM "{table}"
                    """
                ).fetchone()[0]

            print(
                f"{label:<44}"
                f"{rows:>12,}"
                f"{contracts:>14}"
            )

        alt_table = (
            "bid_tab_subcontractor_"
            "relationship_2025_alt_candidate_v2"
        )

        if table_exists(
            con,
            alt_table,
        ):
            print()
            print("ALTERNATE RELATIONSHIP CANDIDATE")
            print("-" * 140)

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

                    FROM {alt_table}

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
            "bid_tab_subcontractor_"
            "quarantined_2025_v1"
        )

        if table_exists(
            con,
            quarantine_table,
        ):
            print()
            print("QUARANTINE")
            print("-" * 140)

            print(
                con.execute(
                    f"""
                    SELECT
                        contract_number,
                        authoritative_rank_count,
                        disclosure_block_count,
                        quarantine_reason,
                        resolution_status

                    FROM {quarantine_table}

                    ORDER BY
                        contract_number
                    """
                ).fetchdf().to_string(
                    index=False
                )
            )

        latest_backup = collect_files(
            paths["backups"],
            "*.duckdb",
            1,
        )

        print()
        print("LATEST BACKUP")
        print("-" * 140)

        if latest_backup:
            backup = latest_backup[0]

            print(
                f"{backup.name} | "
                f"{format_bytes(backup.stat().st_size)}"
            )
        else:
            print("No backup found.")

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
        help="Create and validate a database backup.",
    )

    backup_parser.add_argument(
        "--reason",
        default="manual",
        help="Short reason included in the backup filename.",
    )

    backup_parser.add_argument(
        "--checksum",
        action="store_true",
        help="Validate the backup using SHA256 checksums.",
    )

    logs_parser = subparsers.add_parser(
        "logs",
        help="List recent logs, reports, and backups.",
    )

    logs_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum files shown in each category.",
    )

    subparsers.add_parser(
        "report",
        help="Show the consolidated pipeline report.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.operation == "backup":
        return command_backup(
            arguments.reason,
            arguments.checksum,
        )

    if arguments.operation == "logs":
        return command_logs(
            arguments.limit
        )

    if arguments.operation == "report":
        return command_report()

    parser.error(
        f"Unsupported operation: {arguments.operation}"
    )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
