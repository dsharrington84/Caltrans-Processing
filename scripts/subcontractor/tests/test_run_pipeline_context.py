from __future__ import annotations

from scripts.subcontractor.framework import (
    FrameworkContext,
)
from scripts.subcontractor.run_pipeline import (
    pipeline_config_from_context,
)


def main() -> int:
    context = FrameworkContext.load()

    config = pipeline_config_from_context(
        context
    )

    if config.project_root != context.paths.project_root:
        raise RuntimeError(
            "Project-root mapping failed."
        )

    if config.database_path != context.paths.database:
        raise RuntimeError(
            "Database-path mapping failed."
        )

    if config.backup_directory != context.paths.backups:
        raise RuntimeError(
            "Backup-directory mapping failed."
        )

    if config.cache_directory != context.paths.cache:
        raise RuntimeError(
            "Cache-directory mapping failed."
        )

    if config.log_directory != context.paths.logs:
        raise RuntimeError(
            "Log-directory mapping failed."
        )

    if config.target_year != context.target_year:
        raise RuntimeError(
            "Target-year mapping failed."
        )

    if config.target_districts != context.target_districts:
        raise RuntimeError(
            "Target-district mapping failed."
        )

    if config.tables != context.tables:
        raise RuntimeError(
            "Configured-table mapping failed."
        )

    print()
    print("RUN PIPELINE CONTEXT TEST PASSED")
    print(f"Database: {config.database_path}")
    print(f"Target year: {config.target_year}")
    print(
        "Target districts: "
        + ", ".join(
            str(value)
            for value in config.target_districts
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
