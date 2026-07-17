from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = (
    PROJECT_ROOT
    / "config/subcontractor/settings.json"
)

DEFAULT_DATABASE_PATH = (
    PROJECT_ROOT
    / "data/database/caltrans_pricing.duckdb"
)

DEFAULT_BACKUP_DIRECTORY = (
    PROJECT_ROOT
    / "data/database/backups"
)

DEFAULT_LOG_DIRECTORY = (
    PROJECT_ROOT
    / "data/logs/subcontractor"
)

DEFAULT_REPORT_DIRECTORY = (
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
        value = json.load(file)

    if not isinstance(value, dict):
        raise TypeError(
            "Subcontractor settings must contain "
            "a JSON object."
        )

    return value


def find_setting(
    settings: dict[str, Any],
    candidates: tuple[str, ...],
) -> Any:
    for candidate in candidates:
        if candidate in settings:
            return settings[candidate]

    for value in settings.values():
        if not isinstance(value, dict):
            continue

        result = find_setting(
            value,
            candidates,
        )

        if result is not None:
            return result

    return None


def resolve_path(
    value: Any,
    default: Path,
) -> Path:
    if value in {
        None,
        "",
    }:
        return default.resolve()

    path = Path(str(value)).expanduser()

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def get_paths(
    settings: dict[str, Any],
) -> dict[str, Path]:
    database_path = resolve_path(
        find_setting(
            settings,
            (
                "database_path",
                "database",
                "duckdb_path",
            ),
        ),
        DEFAULT_DATABASE_PATH,
    )

    backup_directory = resolve_path(
        find_setting(
            settings,
            (
                "backup_directory",
                "backup_dir",
            ),
        ),
        DEFAULT_BACKUP_DIRECTORY,
    )

    log_directory = resolve_path(
        find_setting(
            settings,
            (
                "log_directory",
                "log_dir",
            ),
        ),
        DEFAULT_LOG_DIRECTORY,
    )

    report_directory = resolve_path(
        find_setting(
            settings,
            (
                "report_directory",
                "report_dir",
            ),
        ),
        DEFAULT_REPORT_DIRECTORY,
    )

    return {
        "database": database_path,
        "backups": backup_directory,
        "logs": log_directory,
        "reports": report_directory,
    }


def format_bytes(
    value: int,
) -> str:
    units = (
        "B",
        "KB",
        "MB",
        "GB",
        "TB",
    )

    amount = float(value)

    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount):,} {unit}"

            return f"{amount:,.1f} {unit}"

        amount /= 1024

    return f"{value:,} B"


def format_timestamp(
    timestamp: float,
) -> str:
    return datetime.fromtimestamp(
        timestamp
    ).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )


def newest_file(
    directory: Path,
    pattern: str = "*",
) -> Path | None:
    if not directory.exists():
        return None

    files = [
        path
        for path in directory.glob(pattern)
        if path.is_file()
    ]

    if not files:
        return None

    return max(
        files,
        key=lambda path: path.stat().st_mtime,
    )


def run_git(
    *arguments: str,
) -> str | None:
    if not shutil.which("git"):
        return None

    completed = subprocess.run(
        [
            "git",
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        return None

    return completed.stdout.strip()


def print_check(
    passed: bool,
    name: str,
    detail: str,
) -> None:
    symbol = "PASS" if passed else "FAIL"

    print(
        f"{symbol:<6} "
        f"{name:<30} "
        f"{detail}"
    )


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


def command_doctor() -> int:
    print()
    print("SUBCONTRACTOR FRAMEWORK DOCTOR")
    print("=" * 120)

    failures = 0

    print()
    print("PYTHON")
    print("-" * 120)

    virtual_environment = (
        sys.prefix != sys.base_prefix
    )

    print_check(
        virtual_environment,
        "Virtual environment",
        sys.prefix,
    )

    if not virtual_environment:
        failures += 1

    version_ok = sys.version_info >= (
        3,
        12,
    )

    print_check(
        version_ok,
        "Python version",
        sys.version.split()[0],
    )

    if not version_ok:
        failures += 1

    print()
    print("PROJECT")
    print("-" * 120)

    print_check(
        PROJECT_ROOT.exists(),
        "Project root",
        str(PROJECT_ROOT),
    )

    config_exists = CONFIG_PATH.exists()

    print_check(
        config_exists,
        "Configuration",
        str(CONFIG_PATH),
    )

    if not config_exists:
        failures += 1

    try:
        settings = load_settings()
        config_valid = True
        config_detail = (
            f"{len(settings)} top-level settings"
        )
    except Exception as error:
        settings = {}
        config_valid = False
        config_detail = str(error)
        failures += 1

    print_check(
        config_valid,
        "Configuration parse",
        config_detail,
    )

    paths = get_paths(
        settings
    )

    print()
    print("DATABASE")
    print("-" * 120)

    database_path = paths["database"]
    database_exists = database_path.exists()

    print_check(
        database_exists,
        "DuckDB file",
        str(database_path),
    )

    if not database_exists:
        failures += 1
    else:
        print_check(
            database_path.stat().st_size > 0,
            "Database size",
            format_bytes(
                database_path.stat().st_size
            ),
        )

        try:
            con = duckdb.connect(
                str(database_path),
                read_only=True,
            )

            try:
                table_count = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    """
                ).fetchone()[0]

                print_check(
                    True,
                    "Database connection",
                    f"{table_count:,} tables",
                )

                important_tables = (
                    "bid_tab_subcontractor_relationship_current",
                    "bid_tab_subcontractor_relationship_normalized_2025_batch1_v1",
                    "bid_tab_subcontractor_disclosure_2025_alt_promoted_v1",
                    "bid_tab_subcontractor_quarantined_2025_v1",
                )

                for table_name in important_tables:
                    exists = table_exists(
                        con,
                        table_name,
                    )

                    print_check(
                        exists,
                        table_name[:30],
                        (
                            "available"
                            if exists
                            else "not found"
                        ),
                    )

            finally:
                con.close()

        except Exception as error:
            print_check(
                False,
                "Database connection",
                str(error),
            )
            failures += 1

    print()
    print("GENERATED OUTPUTS")
    print("-" * 120)

    for label, key in (
        ("Backup directory", "backups"),
        ("Log directory", "logs"),
        ("Report directory", "reports"),
    ):
        path = paths[key]

        print_check(
            path.exists(),
            label,
            str(path),
        )

    latest_backup = newest_file(
        paths["backups"],
        "*.duckdb",
    )

    if latest_backup is None:
        print_check(
            False,
            "Latest backup",
            "No DuckDB backup found",
        )
        failures += 1
    else:
        print_check(
            True,
            "Latest backup",
            (
                f"{latest_backup.name} | "
                f"{format_timestamp(latest_backup.stat().st_mtime)} | "
                f"{format_bytes(latest_backup.stat().st_size)}"
            ),
        )

    latest_log = newest_file(
        paths["logs"],
        "*.log",
    )

    print_check(
        latest_log is not None,
        "Latest log",
        (
            latest_log.name
            if latest_log is not None
            else "No log found"
        ),
    )

    latest_report = newest_file(
        paths["reports"],
    )

    print_check(
        latest_report is not None,
        "Latest report",
        (
            latest_report.name
            if latest_report is not None
            else "No report found"
        ),
    )

    print()
    print("GIT")
    print("-" * 120)

    branch = run_git(
        "branch",
        "--show-current",
    )

    print_check(
        branch is not None,
        "Git repository",
        (
            branch
            if branch
            else "Unavailable"
        ),
    )

    last_commit = run_git(
        "log",
        "-1",
        "--oneline",
    )

    print_check(
        last_commit is not None,
        "Latest commit",
        (
            last_commit
            if last_commit
            else "Unavailable"
        ),
    )

    status = run_git(
        "status",
        "--porcelain",
    )

    if status is None:
        print_check(
            False,
            "Working tree",
            "Unavailable",
        )
    else:
        change_count = len(
            [
                line
                for line in status.splitlines()
                if line.strip()
            ]
        )

        print_check(
            change_count == 0,
            "Working tree",
            (
                "clean"
                if change_count == 0
                else f"{change_count} uncommitted paths"
            ),
        )

    print()
    print("RESULT")
    print("-" * 120)

    if failures:
        print(
            f"Doctor completed with "
            f"{failures} critical failure(s)."
        )
        return 1

    print(
        "Doctor completed without "
        "critical failures."
    )

    return 0


def query_scalar(
    con: duckdb.DuckDBPyConnection,
    query: str,
) -> Any:
    return con.execute(
        query
    ).fetchone()[0]


def command_stats() -> int:
    settings = load_settings()
    paths = get_paths(
        settings
    )

    database_path = paths["database"]

    if not database_path.exists():
        print(
            f"Database not found: {database_path}",
            file=sys.stderr,
        )
        return 1

    con = duckdb.connect(
        str(database_path),
        read_only=True,
    )

    try:
        print()
        print("SUBCONTRACTOR DATASET STATISTICS")
        print("=" * 120)

        datasets = (
            (
                "Current relationships",
                "bid_tab_subcontractor_relationship_current",
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
        print("-" * 120)
        print(
            f"{'Dataset':<42}"
            f"{'Rows':>12}"
            f"{'Contracts':>14}"
        )

        for label, table_name in datasets:
            if not table_exists(
                con,
                table_name,
            ):
                print(
                    f"{label:<42}"
                    f"{'N/A':>12}"
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

            rows = query_scalar(
                con,
                f'SELECT COUNT(*) FROM "{table_name}"',
            )

            if "contract_number" in columns:
                contracts = query_scalar(
                    con,
                    f"""
                    SELECT COUNT(
                        DISTINCT contract_number
                    )
                    FROM "{table_name}"
                    """,
                )
            else:
                contracts = None

            print(
                f"{label:<42}"
                f"{rows:>12,}"
                f"{contracts if contracts is not None else 'N/A':>14}"
            )

        relationship_table = (
            "bid_tab_subcontractor_relationship_current"
        )

        if table_exists(
            con,
            relationship_table,
        ):
            print()
            print("CURRENT RELATIONSHIPS")
            print("-" * 120)

            result = con.execute(
                f"""
                SELECT
                    COUNT(*) AS relationships,
                    COUNT(DISTINCT contract_number)
                        AS contracts,
                    COUNT(DISTINCT prime_bidder_id)
                        AS prime_bidders,
                    COUNT(DISTINCT subcontractor_name)
                        AS subcontractors,
                    COUNT(*) FILTER (
                        WHERE eligible_for_prime_pricing_analysis
                    ) AS pricing_eligible,
                    COUNT(*) FILTER (
                        WHERE prime_bidder_name IS NULL
                           OR TRIM(prime_bidder_name) = ''
                    ) AS prime_identity_gaps

                FROM {relationship_table}
                """
            ).fetchdf()

            print(
                result.to_string(
                    index=False
                )
            )

        quarantine_table = (
            "bid_tab_subcontractor_quarantined_2025_v1"
        )

        if table_exists(
            con,
            quarantine_table,
        ):
            print()
            print("QUARANTINE")
            print("-" * 120)

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

                    FROM {quarantine_table}

                    GROUP BY
                        quarantine_reason

                    ORDER BY
                        quarantine_reason
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
            con,
            alternate_table,
        ):
            print()
            print("ALTERNATE CANDIDATE V2")
            print("-" * 120)

            print(
                con.execute(
                    f"""
                    SELECT
                        contract_number,
                        COUNT(*) AS relationships,
                        COUNT(DISTINCT prime_bidder_id)
                            AS prime_bidders,
                        SUM(disclosure_rows)
                            AS disclosure_rows,
                        COUNT(*) FILTER (
                            WHERE production_identity_class
                                = 'PRIME_IDENTITY_GAP'
                        ) AS identity_gap_relationships

                    FROM {alternate_table}

                    GROUP BY
                        contract_number

                    ORDER BY
                        contract_number
                    """
                ).fetchdf().to_string(
                    index=False
                )
            )

    finally:
        con.close()

    return 0


def print_json_value(
    value: Any,
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
                print_json_value(
                    child,
                    indent + 2,
                )
            else:
                print(
                    f"{prefix}{key}: {child}"
                )

    elif isinstance(value, list):
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
                print_json_value(
                    child,
                    indent + 2,
                )
            else:
                print(
                    f"{prefix}- {child}"
                )

    else:
        print(
            f"{prefix}{value}"
        )


def command_config_show(
    raw_json: bool,
) -> int:
    print()
    print("SUBCONTRACTOR CONFIGURATION")
    print("=" * 120)
    print(f"Source: {CONFIG_PATH}")
    print()

    if not CONFIG_PATH.exists():
        print(
            "Configuration file not found.",
            file=sys.stderr,
        )
        return 1

    settings = load_settings()

    if raw_json:
        print(
            json.dumps(
                settings,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_json_value(
            settings
        )

        print()
        print("RESOLVED PATHS")
        print("-" * 120)

        for name, path in get_paths(
            settings
        ).items():
            print(
                f"{name:<14} {path}"
            )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operational commands for the "
            "subcontractor-processing framework."
        )
    )

    subparsers = parser.add_subparsers(
        dest="operation",
        required=True,
    )

    subparsers.add_parser(
        "doctor",
        help="Check framework health.",
    )

    subparsers.add_parser(
        "stats",
        help="Show production and pipeline statistics.",
    )

    config_parser = subparsers.add_parser(
        "config-show",
        help="Display resolved configuration.",
    )

    config_parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw formatted JSON.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.operation == "doctor":
        return command_doctor()

    if arguments.operation == "stats":
        return command_stats()

    if arguments.operation == "config-show":
        return command_config_show(
            arguments.json
        )

    parser.error(
        f"Unsupported operation: "
        f"{arguments.operation}"
    )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
