from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import duckdb

from scripts.subcontractor.framework import (
    FrameworkContext,
)


CONTRACT_PATTERN = re.compile(
    r"(?i)(?<![A-Z0-9])"
    r"(\d{2}-[A-Z0-9]{6})"
    r"(?![A-Z0-9])"
)

CURRENT_TABLE = (
    "bid_tab_subcontractor_relationship_current"
)

NORMALIZED_TABLES = (
    "bid_tab_subcontractor_relationship_"
    "normalized_2025_v2",
    "bid_tab_subcontractor_relationship_"
    "normalized_2025_batch1_v1",
)

PROMOTED_TABLES = (
    "bid_tab_subcontractor_disclosure_"
    "2025_alt_promoted_v1",
)

STATUS_ORDER = (
    "CURRENT",
    "NORMALIZED_NOT_CURRENT",
    "PROMOTED",
    "READY_FOR_PARSE",
    "DUPLICATE_FILE",
    "INVALID_FILENAME",
)


@dataclass(frozen=True)
class IntakeRecord:
    contract_number: str
    filename: str
    full_path: str
    size_bytes: int
    modified_at: str
    sha256: str
    duplicate_group_size: int
    duplicate_sequence: int
    pipeline_status: str
    underlying_status: str
    in_current: bool
    in_normalized: bool
    in_promoted: bool


def quote_identifier(
    value: str,
) -> str:
    return (
        '"'
        + value.replace('"', '""')
        + '"'
    )


def extract_contract_number(
    filename: str,
) -> str:
    match = CONTRACT_PATTERN.search(
        filename
    )

    if match is None:
        return ""

    return match.group(1).upper()


def calculate_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def table_exists(
    context: FrameworkContext,
    con: duckdb.DuckDBPyConnection,
    table_name: str,
) -> bool:
    return context.table_exists(
        table_name,
        connection=con,
    )


def load_contracts(
    *,
    context: FrameworkContext,
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    target_year: int | None,
) -> set[str]:
    if not table_exists(
        context,
        con,
        table_name,
    ):
        return set()

    columns = {
        row[0]
        for row in con.execute(
            f'DESCRIBE '
            f'{quote_identifier(table_name)}'
        ).fetchall()
    }

    if "contract_number" not in columns:
        return set()

    filters = [
        "contract_number IS NOT NULL",
        "TRIM(contract_number) <> ''",
    ]

    parameters: list[object] = []

    if target_year is not None:
        if "bid_opening_date" in columns:
            filters.append(
                "EXTRACT(YEAR FROM "
                "bid_opening_date) = ?"
            )
            parameters.append(
                target_year
            )
        elif "bid_year" in columns:
            filters.append(
                "CAST(bid_year AS INTEGER) = ?"
            )
            parameters.append(
                target_year
            )

    rows = con.execute(
        f"""
        SELECT DISTINCT
            UPPER(
                TRIM(contract_number)
            ) AS contract_number
        FROM {quote_identifier(table_name)}
        WHERE {" AND ".join(filters)}
        """,
        parameters,
    ).fetchall()

    return {
        str(row[0])
        for row in rows
        if row[0]
    }


def select_underlying_status(
    *,
    contract_number: str,
    current_contracts: set[str],
    normalized_contracts: set[str],
    promoted_contracts: set[str],
) -> str:
    if not contract_number:
        return "INVALID_FILENAME"

    if contract_number in current_contracts:
        return "CURRENT"

    if contract_number in normalized_contracts:
        return "NORMALIZED_NOT_CURRENT"

    if contract_number in promoted_contracts:
        return "PROMOTED"

    return "READY_FOR_PARSE"


def build_records(
    *,
    folder: Path,
    current_contracts: set[str],
    normalized_contracts: set[str],
    promoted_contracts: set[str],
    recursive: bool,
    include_hashes: bool,
) -> list[IntakeRecord]:
    if recursive:
        pdf_paths = sorted(
            path
            for path in folder.rglob("*")
            if (
                path.is_file()
                and path.suffix.lower() == ".pdf"
            )
        )
    else:
        pdf_paths = sorted(
            path
            for path in folder.iterdir()
            if (
                path.is_file()
                and path.suffix.lower() == ".pdf"
            )
        )

    contract_numbers = [
        extract_contract_number(
            path.name
        )
        for path in pdf_paths
    ]

    group_sizes = Counter(
        value
        for value in contract_numbers
        if value
    )

    sequence_by_contract: Counter[str] = (
        Counter()
    )

    records: list[IntakeRecord] = []

    for path, contract_number in zip(
        pdf_paths,
        contract_numbers,
        strict=True,
    ):
        if contract_number:
            sequence_by_contract[
                contract_number
            ] += 1

            duplicate_sequence = (
                sequence_by_contract[
                    contract_number
                ]
            )

            duplicate_group_size = (
                group_sizes[
                    contract_number
                ]
            )
        else:
            duplicate_sequence = 0
            duplicate_group_size = 0

        underlying_status = (
            select_underlying_status(
                contract_number=(
                    contract_number
                ),
                current_contracts=(
                    current_contracts
                ),
                normalized_contracts=(
                    normalized_contracts
                ),
                promoted_contracts=(
                    promoted_contracts
                ),
            )
        )

        if (
            contract_number
            and duplicate_sequence > 1
        ):
            pipeline_status = (
                "DUPLICATE_FILE"
            )
        else:
            pipeline_status = (
                underlying_status
            )

        stat = path.stat()

        records.append(
            IntakeRecord(
                contract_number=(
                    contract_number
                ),
                filename=path.name,
                full_path=str(
                    path.resolve()
                ),
                size_bytes=stat.st_size,
                modified_at=(
                    datetime.fromtimestamp(
                        stat.st_mtime
                    ).isoformat(
                        timespec="seconds"
                    )
                ),
                sha256=(
                    calculate_sha256(path)
                    if include_hashes
                    else ""
                ),
                duplicate_group_size=(
                    duplicate_group_size
                ),
                duplicate_sequence=(
                    duplicate_sequence
                ),
                pipeline_status=(
                    pipeline_status
                ),
                underlying_status=(
                    underlying_status
                ),
                in_current=(
                    contract_number
                    in current_contracts
                ),
                in_normalized=(
                    contract_number
                    in normalized_contracts
                ),
                in_promoted=(
                    contract_number
                    in promoted_contracts
                ),
            )
        )

    return records


def write_manifest(
    *,
    records: Iterable[IntakeRecord],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = [
        asdict(record)
        for record in records
    ]

    fieldnames = [
        field.name
        for field in IntakeRecord.__dataclass_fields__.values()
    ]

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def print_summary(
    *,
    folder: Path,
    records: list[IntakeRecord],
    manifest_path: Path,
) -> None:
    status_counts = Counter(
        record.pipeline_status
        for record in records
    )

    contracts = {
        record.contract_number
        for record in records
        if record.contract_number
    }

    duplicate_contracts = {
        record.contract_number
        for record in records
        if (
            record.contract_number
            and record.duplicate_group_size > 1
        )
    }

    represented_contracts = {
        record.contract_number
        for record in records
        if (
            record.contract_number
            and record.underlying_status
            in {
                "CURRENT",
                "NORMALIZED_NOT_CURRENT",
                "PROMOTED",
            }
        )
    }

    ready_contracts = {
        record.contract_number
        for record in records
        if (
            record.contract_number
            and record.underlying_status
            == "READY_FOR_PARSE"
        )
    }

    total_contracts = len(
        contracts
    )

    represented_pct = (
        100.0
        * len(represented_contracts)
        / total_contracts
        if total_contracts
        else 0.0
    )

    print()
    print("FOLDER INTAKE REPORT")
    print("=" * 130)
    print(f"Folder:             {folder}")
    print(f"Manifest:           {manifest_path}")
    print(f"PDF files:          {len(records):,}")
    print(f"Distinct contracts: {total_contracts:,}")
    print(
        f"Represented:        "
        f"{len(represented_contracts):,} "
        f"({represented_pct:.2f}%)"
    )
    print(
        f"Ready for parse:    "
        f"{len(ready_contracts):,}"
    )
    print(
        f"Duplicate contracts:"
        f" {len(duplicate_contracts):,}"
    )

    print()
    print("FILE STATUS COUNTS")
    print("-" * 130)

    for status in STATUS_ORDER:
        print(
            f"{status:<30}"
            f"{status_counts.get(status, 0):>8,}"
        )

    print()
    print("READY CONTRACTS")
    print("-" * 130)

    if ready_contracts:
        for contract in sorted(
            ready_contracts
        ):
            print(contract)
    else:
        print("None")

    normalized_not_current = {
        record.contract_number
        for record in records
        if (
            record.contract_number
            and record.underlying_status
            == "NORMALIZED_NOT_CURRENT"
        )
    }

    print()
    print("NORMALIZED BUT NOT CURRENT")
    print("-" * 130)

    if normalized_not_current:
        for contract in sorted(
            normalized_not_current
        ):
            print(contract)
    else:
        print("None")

    print()
    print("DUPLICATE PDF GROUPS")
    print("-" * 130)

    if duplicate_contracts:
        for contract in sorted(
            duplicate_contracts
        ):
            filenames = [
                record.filename
                for record in records
                if (
                    record.contract_number
                    == contract
                )
            ]

            print(
                f"{contract}: "
                + " | ".join(filenames)
            )
    else:
        print("None")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory a PDF folder and classify "
            "contracts against subcontractor "
            "production datasets."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help=(
            "Folder containing bid-tab PDF files."
        ),
    )

    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help=(
            "Optional bid year used when filtering "
            "production datasets. Defaults to the "
            "configured framework target year."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional manifest CSV path."
        ),
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "Scan nested folders recursively."
        ),
    )

    parser.add_argument(
        "--hash",
        action="store_true",
        dest="include_hashes",
        help=(
            "Calculate SHA256 for each PDF."
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()

    context = FrameworkContext.load()

    folder = arguments.folder.expanduser()

    if not folder.is_absolute():
        folder = (
            Path.cwd()
            / folder
        )

    folder = folder.resolve()

    if not folder.exists():
        parser.error(
            f"Folder does not exist: {folder}"
        )

    if not folder.is_dir():
        parser.error(
            f"Not a directory: {folder}"
        )

    target_year = (
        arguments.year
        if arguments.year is not None
        else context.target_year
    )

    con = context.connect(
        read_only=True,
    )

    try:
        current_contracts = (
            load_contracts(
                context=context,
                con=con,
                table_name=CURRENT_TABLE,
                target_year=target_year,
            )
        )

        normalized_contracts: set[str] = (
            set()
        )

        for table_name in NORMALIZED_TABLES:
            normalized_contracts.update(
                load_contracts(
                    context=context,
                    con=con,
                    table_name=table_name,
                    target_year=target_year,
                )
            )

        promoted_contracts: set[str] = (
            set()
        )

        for table_name in PROMOTED_TABLES:
            promoted_contracts.update(
                load_contracts(
                    context=context,
                    con=con,
                    table_name=table_name,
                    target_year=target_year,
                )
            )

    finally:
        con.close()

    records = build_records(
        folder=folder,
        current_contracts=(
            current_contracts
        ),
        normalized_contracts=(
            normalized_contracts
        ),
        promoted_contracts=(
            promoted_contracts
        ),
        recursive=arguments.recursive,
        include_hashes=(
            arguments.include_hashes
        ),
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    if arguments.output is None:
        output_path = (
            context.paths.project_root
            / "data"
            / "intake"
            / (
                f"folder_intake_{target_year}_"
                f"{timestamp}.csv"
            )
        )
    else:
        output_path = (
            arguments.output.expanduser()
        )

        if not output_path.is_absolute():
            output_path = (
                context.paths.project_root
                / output_path
            )

    write_manifest(
        records=records,
        output_path=output_path,
    )

    print_summary(
        folder=folder,
        records=records,
        manifest_path=output_path,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
