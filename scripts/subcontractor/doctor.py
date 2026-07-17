from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Callable

from scripts.subcontractor.framework import (
    FrameworkContext,
)


class Severity(IntEnum):
    PASS = 0
    WARN = 1
    FAIL = 2


@dataclass(frozen=True)
class HealthCheck:
    section: str
    name: str
    severity: Severity
    detail: str


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


def newest_file(
    directory: Path,
    pattern: str = "*",
) -> Path | None:
    if not directory.exists():
        return None

    files = [
        path
        for path in directory.glob(
            pattern
        )
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
) -> tuple[int, str]:
    if shutil.which("git") is None:
        return 127, "Git executable not found"

    completed = subprocess.run(
        [
            "git",
            *arguments,
        ],
        cwd=FrameworkContext.load().paths.project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    output = (
        completed.stdout.strip()
        or completed.stderr.strip()
    )

    return completed.returncode, output


def add_check(
    checks: list[HealthCheck],
    section: str,
    name: str,
    severity: Severity,
    detail: str,
) -> None:
    checks.append(
        HealthCheck(
            section=section,
            name=name,
            severity=severity,
            detail=detail,
        )
    )


def collect_checks(
    context: FrameworkContext,
) -> list[HealthCheck]:
    checks: list[HealthCheck] = []

    virtual_environment = (
        sys.prefix != sys.base_prefix
    )

    add_check(
        checks,
        "Python",
        "Virtual environment",
        (
            Severity.PASS
            if virtual_environment
            else Severity.FAIL
        ),
        sys.prefix,
    )

    python_ok = (
        sys.version_info >= (3, 12)
    )

    add_check(
        checks,
        "Python",
        "Python version",
        (
            Severity.PASS
            if python_ok
            else Severity.FAIL
        ),
        sys.version.split()[0],
    )

    add_check(
        checks,
        "Project",
        "Project root",
        (
            Severity.PASS
            if context.paths.project_root.exists()
            else Severity.FAIL
        ),
        str(context.paths.project_root),
    )

    add_check(
        checks,
        "Project",
        "Configuration",
        (
            Severity.PASS
            if context.paths.config.exists()
            else Severity.FAIL
        ),
        str(context.paths.config),
    )

    add_check(
        checks,
        "Project",
        "Target year",
        (
            Severity.PASS
            if context.target_year is not None
            else Severity.WARN
        ),
        str(context.target_year),
    )

    add_check(
        checks,
        "Project",
        "Target districts",
        (
            Severity.PASS
            if context.target_districts
            else Severity.WARN
        ),
        (
            ", ".join(
                str(value)
                for value in context.target_districts
            )
            or "None configured"
        ),
    )

    database = context.paths.database

    if not database.exists():
        add_check(
            checks,
            "Database",
            "DuckDB file",
            Severity.FAIL,
            str(database),
        )
    else:
        add_check(
            checks,
            "Database",
            "DuckDB file",
            Severity.PASS,
            str(database),
        )

        add_check(
            checks,
            "Database",
            "Database size",
            (
                Severity.PASS
                if database.stat().st_size > 0
                else Severity.FAIL
            ),
            format_bytes(
                database.stat().st_size
            ),
        )

        try:
            con = context.connect(
                read_only=True
            )

            try:
                table_count = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    """
                ).fetchone()[0]

                add_check(
                    checks,
                    "Database",
                    "Database connection",
                    Severity.PASS,
                    f"{table_count:,} tables",
                )

                important_tables = (
                    "bid_tab_subcontractor_relationship_current",
                    "bid_tab_subcontractor_relationship_normalized_2025_batch1_v1",
                    "bid_tab_subcontractor_disclosure_2025_alt_promoted_v1",
                    "bid_tab_subcontractor_quarantined_2025_v1",
                )

                for table_name in important_tables:
                    exists = context.table_exists(
                        table_name,
                        connection=con,
                    )

                    add_check(
                        checks,
                        "Database",
                        table_name,
                        (
                            Severity.PASS
                            if exists
                            else Severity.WARN
                        ),
                        (
                            "available"
                            if exists
                            else "not found"
                        ),
                    )

            finally:
                con.close()

        except Exception as error:
            add_check(
                checks,
                "Database",
                "Database connection",
                Severity.FAIL,
                str(error),
            )

    directories = (
        (
            "Backup directory",
            context.paths.backups,
        ),
        (
            "Cache directory",
            context.paths.cache,
        ),
        (
            "Log directory",
            context.paths.logs,
        ),
        (
            "Report directory",
            context.paths.reports,
        ),
    )

    for label, directory in directories:
        add_check(
            checks,
            "Generated outputs",
            label,
            (
                Severity.PASS
                if directory.exists()
                else Severity.WARN
            ),
            str(directory),
        )

    latest_backup = newest_file(
        context.paths.backups,
        "*.duckdb",
    )

    if latest_backup is None:
        add_check(
            checks,
            "Generated outputs",
            "Latest backup",
            Severity.WARN,
            "No DuckDB backup found",
        )
    else:
        modified = datetime.fromtimestamp(
            latest_backup.stat().st_mtime
        ).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )

        add_check(
            checks,
            "Generated outputs",
            "Latest backup",
            Severity.PASS,
            (
                f"{latest_backup.name} | "
                f"{modified} | "
                f"{format_bytes(latest_backup.stat().st_size)}"
            ),
        )

    latest_log = newest_file(
        context.paths.logs,
        "*.log",
    )

    add_check(
        checks,
        "Generated outputs",
        "Latest log",
        (
            Severity.PASS
            if latest_log is not None
            else Severity.WARN
        ),
        (
            latest_log.name
            if latest_log is not None
            else "No log found"
        ),
    )

    latest_report = newest_file(
        context.paths.reports,
    )

    add_check(
        checks,
        "Generated outputs",
        "Latest report",
        (
            Severity.PASS
            if latest_report is not None
            else Severity.WARN
        ),
        (
            latest_report.name
            if latest_report is not None
            else "No report found"
        ),
    )

    branch_code, branch = run_git(
        "branch",
        "--show-current",
    )

    add_check(
        checks,
        "Git",
        "Repository",
        (
            Severity.PASS
            if branch_code == 0
            else Severity.WARN
        ),
        branch or "Unavailable",
    )

    commit_code, commit = run_git(
        "log",
        "-1",
        "--oneline",
    )

    add_check(
        checks,
        "Git",
        "Latest commit",
        (
            Severity.PASS
            if commit_code == 0
            else Severity.WARN
        ),
        commit or "Unavailable",
    )

    status_code, status = run_git(
        "status",
        "--porcelain",
    )

    if status_code != 0:
        add_check(
            checks,
            "Git",
            "Working tree",
            Severity.WARN,
            status or "Unavailable",
        )
    else:
        changed_paths = [
            line
            for line in status.splitlines()
            if line.strip()
        ]

        add_check(
            checks,
            "Git",
            "Working tree",
            (
                Severity.PASS
                if not changed_paths
                else Severity.WARN
            ),
            (
                "clean"
                if not changed_paths
                else (
                    f"{len(changed_paths)} "
                    "uncommitted paths"
                )
            ),
        )

    return checks


def print_checks(
    checks: list[HealthCheck],
) -> None:
    current_section: str | None = None

    for check in checks:
        if check.section != current_section:
            current_section = check.section

            print()
            print(
                current_section.upper()
            )
            print("-" * 140)

        print(
            f"{check.severity.name:<6} "
            f"{check.name:<48} "
            f"{check.detail}"
        )


def main() -> int:
    print()
    print("SUBCONTRACTOR FRAMEWORK DOCTOR")
    print("=" * 140)

    try:
        context = FrameworkContext.load()
        checks = collect_checks(
            context
        )
    except Exception as error:
        print()
        print(
            f"FAIL   Framework initialization: {error}"
        )
        return 1

    print_checks(
        checks
    )

    pass_count = sum(
        check.severity == Severity.PASS
        for check in checks
    )

    warning_count = sum(
        check.severity == Severity.WARN
        for check in checks
    )

    failure_count = sum(
        check.severity == Severity.FAIL
        for check in checks
    )

    print()
    print("RESULT")
    print("-" * 140)
    print(f"Passes: {pass_count}")
    print(f"Warnings: {warning_count}")
    print(f"Failures: {failure_count}")

    if failure_count:
        print()
        print(
            "Doctor completed with "
            f"{failure_count} critical failure(s)."
        )
        return 1

    if warning_count:
        print()
        print(
            "Doctor completed without critical "
            f"failures and with {warning_count} warning(s)."
        )
        return 0

    print()
    print(
        "Doctor completed without warnings "
        "or critical failures."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
