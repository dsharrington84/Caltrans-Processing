from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import duckdb

from scripts.subcontractor.database import (
    object_exists,
    quote_identifier,
)


@dataclass(frozen=True)
class ValidationResult:
    check_name: str
    passed: bool
    observed_value: object
    expected_value: object | None
    detail: str


def validate_required_columns(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    required_columns: Iterable[str],
) -> ValidationResult:
    if not object_exists(
        connection,
        table_name,
    ):
        return ValidationResult(
            check_name=(
                f"{table_name}: required columns"
            ),
            passed=False,
            observed_value="TABLE_MISSING",
            expected_value=list(required_columns),
            detail=(
                f"Database object does not exist: "
                f"{table_name}"
            ),
        )

    table_literal = table_name.replace(
        "'",
        "''",
    )

    frame = connection.execute(
        f"""
        SELECT
            column_name

        FROM information_schema.columns

        WHERE table_name = '{table_literal}'
        """
    ).fetchdf()

    available = set(
        frame["column_name"].tolist()
    )

    required = set(
        required_columns
    )

    missing = sorted(
        required - available
    )

    return ValidationResult(
        check_name=(
            f"{table_name}: required columns"
        ),
        passed=not missing,
        observed_value=(
            sorted(available)
        ),
        expected_value=(
            sorted(required)
        ),
        detail=(
            "All required columns found."
            if not missing
            else (
                "Missing columns: "
                + ", ".join(missing)
            )
        ),
    )


def validate_no_nulls(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: Iterable[str],
) -> list[ValidationResult]:
    table = quote_identifier(
        table_name
    )

    results: list[ValidationResult] = []

    for column_name in columns:
        column = quote_identifier(
            column_name
        )

        null_count = int(
            connection.execute(
                f"""
                SELECT COUNT(*)

                FROM {table}

                WHERE {column} IS NULL
                """
            ).fetchone()[0]
        )

        results.append(
            ValidationResult(
                check_name=(
                    f"{table_name}.{column_name}: null count"
                ),
                passed=(
                    null_count == 0
                ),
                observed_value=null_count,
                expected_value=0,
                detail=(
                    "No null values found."
                    if null_count == 0
                    else (
                        f"Found {null_count:,} "
                        "null values."
                    )
                ),
            )
        )

    return results


def validate_unique_key(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    key_columns: Iterable[str],
) -> ValidationResult:
    columns = list(
        key_columns
    )

    table = quote_identifier(
        table_name
    )

    quoted_columns = [
        quote_identifier(column)
        for column in columns
    ]

    grouping = ", ".join(
        quoted_columns
    )

    duplicate_groups = int(
        connection.execute(
            f"""
            SELECT COUNT(*)

            FROM (
                SELECT
                    {grouping},
                    COUNT(*) AS row_count

                FROM {table}

                GROUP BY
                    {grouping}

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    return ValidationResult(
        check_name=(
            f"{table_name}: unique key "
            f"({', '.join(columns)})"
        ),
        passed=(
            duplicate_groups == 0
        ),
        observed_value=duplicate_groups,
        expected_value=0,
        detail=(
            "No duplicate key groups found."
            if duplicate_groups == 0
            else (
                f"Found {duplicate_groups:,} "
                "duplicate key groups."
            )
        ),
    )


def validate_contract_set_match(
    connection: duckdb.DuckDBPyConnection,
    left_table: str,
    right_table: str,
    *,
    contract_column: str = "contract_number",
) -> ValidationResult:
    left = quote_identifier(
        left_table
    )

    right = quote_identifier(
        right_table
    )

    column = quote_identifier(
        contract_column
    )

    mismatch_count = int(
        connection.execute(
            f"""
            SELECT COUNT(*)

            FROM (
                SELECT DISTINCT
                    {column} AS contract_number

                FROM {left}
            ) left_contracts

            FULL OUTER JOIN (
                SELECT DISTINCT
                    {column} AS contract_number

                FROM {right}
            ) right_contracts
                ON right_contracts.contract_number
                    = left_contracts.contract_number

            WHERE left_contracts.contract_number
                    IS NULL
               OR right_contracts.contract_number
                    IS NULL
            """
        ).fetchone()[0]
    )

    return ValidationResult(
        check_name=(
            f"Contract set: "
            f"{left_table} vs {right_table}"
        ),
        passed=(
            mismatch_count == 0
        ),
        observed_value=mismatch_count,
        expected_value=0,
        detail=(
            "Contract sets match."
            if mismatch_count == 0
            else (
                f"Found {mismatch_count:,} "
                "contract-set mismatches."
            )
        ),
    )


def validate_child_contracts_in_parent(
    connection: duckdb.DuckDBPyConnection,
    parent_table: str,
    child_table: str,
    *,
    contract_column: str = "contract_number",
) -> ValidationResult:
    parent = quote_identifier(
        parent_table
    )

    child = quote_identifier(
        child_table
    )

    column = quote_identifier(
        contract_column
    )

    orphan_count = int(
        connection.execute(
            f"""
            SELECT COUNT(*)

            FROM (
                SELECT DISTINCT
                    {column} AS contract_number

                FROM {child}
            ) child_contracts

            LEFT JOIN (
                SELECT DISTINCT
                    {column} AS contract_number

                FROM {parent}
            ) parent_contracts
                ON parent_contracts.contract_number
                    = child_contracts.contract_number

            WHERE parent_contracts.contract_number
                    IS NULL
            """
        ).fetchone()[0]
    )

    return ValidationResult(
        check_name=(
            f"Child contracts: "
            f"{child_table} within {parent_table}"
        ),
        passed=(
            orphan_count == 0
        ),
        observed_value=orphan_count,
        expected_value=0,
        detail=(
            "All child contracts exist in parent."
            if orphan_count == 0
            else (
                f"Found {orphan_count:,} "
                "orphan child contracts."
            )
        ),
    )


def validate_status_counts(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    status_column: str,
) -> dict[str, int]:
    table = quote_identifier(
        table_name
    )

    status = quote_identifier(
        status_column
    )

    frame = connection.execute(
        f"""
        SELECT
            COALESCE(
                CAST({status} AS VARCHAR),
                '<NULL>'
            ) AS status_value,
            COUNT(*) AS row_count

        FROM {table}

        GROUP BY
            status_value

        ORDER BY
            row_count DESC,
            status_value
        """
    ).fetchdf()

    return {
        str(row.status_value): int(
            row.row_count
        )
        for row in frame.itertuples(
            index=False
        )
    }


def all_passed(
    results: Iterable[ValidationResult],
) -> bool:
    return all(
        result.passed
        for result in results
    )
