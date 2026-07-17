from __future__ import annotations

from scripts.subcontractor.framework import (
    FrameworkContext,
)


def main() -> int:
    context = FrameworkContext.load()

    if not context.paths.project_root.exists():
        raise RuntimeError(
            "Project root does not exist."
        )

    if not context.paths.config.exists():
        raise RuntimeError(
            "Configuration file does not exist."
        )

    if context.target_year != 2025:
        raise RuntimeError(
            "Expected target year 2025; "
            f"found {context.target_year}."
        )

    if context.target_districts != (
        7,
        8,
        11,
        12,
    ):
        raise RuntimeError(
            "Unexpected target districts: "
            f"{context.target_districts}"
        )

    expected_table_key = "manifest"

    if expected_table_key not in context.tables:
        raise RuntimeError(
            f"Missing configured table: "
            f"{expected_table_key}"
        )

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

    finally:
        con.close()

    if table_count <= 0:
        raise RuntimeError(
            "No DuckDB tables were found."
        )

    print()
    print("FRAMEWORK CONTEXT TEST PASSED")
    print(f"Database: {context.paths.database}")
    print(f"Tables: {table_count}")
    print(f"Target year: {context.target_year}")
    print(
        "Target districts: "
        + ", ".join(
            str(value)
            for value in context.target_districts
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
