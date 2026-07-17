from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.subcontractor.config import PipelineConfig

from scripts.subcontractor.framework import (
    FrameworkContext,
)
from scripts.subcontractor.database import (
    connect_database,
    list_database_objects,
    quote_identifier,
    require_objects,
    table_row_count,
)
from scripts.subcontractor.logging_utils import (
    configure_logging,
    log_key_value,
    log_section,
    log_subsection,
)
from scripts.subcontractor.pdf_cache import (
    text_sha256,
    write_cached_page,
    write_contract_manifest,
)


def run_status(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "status",
    )

    log_section(
        logger,
        "SUBCONTRACTOR PIPELINE STATUS",
        width=140,
    )

    log_key_value(
        logger,
        "Database",
        config.database_path,
    )

    log_key_value(
        logger,
        "Target year",
        config.target_year,
    )

    log_key_value(
        logger,
        "Districts",
        config.target_districts,
    )

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    available_objects = list_database_objects(
        connection
    )

    ordered_keys = [
        "manifest",
        "preflight",
        "parse_plan",
        "page_audit",
        "raw_pages",
        "bidder_sections",
        "disclosure_lines",
        "rejected_lines",
        "stage1_audit",
    ]

    log_subsection(
        logger,
        "CONFIGURED DATABASE OBJECTS",
        width=140,
    )

    logger.info(
        "%-24s %-82s %-12s %12s",
        "Stage object",
        "Database object",
        "Status",
        "Rows",
    )

    logger.info(
        "-" * 140
    )

    missing_objects: list[str] = []

    for key in ordered_keys:
        object_name = config.tables[key]

        exists = (
            object_name
            in available_objects
        )

        row_count = (
            table_row_count(
                connection,
                object_name,
            )
            if exists
            else None
        )

        if not exists:
            missing_objects.append(
                object_name
            )

        logger.info(
            "%-24s %-82s %-12s %12s",
            key,
            object_name,
            (
                "FOUND"
                if exists
                else "MISSING"
            ),
            (
                f"{row_count:,}"
                if row_count is not None
                else "-"
            ),
        )

    connection.close()

    log_subsection(
        logger,
        "STATUS SUMMARY",
        width=140,
    )

    log_key_value(
        logger,
        "Configured objects",
        len(ordered_keys),
    )

    log_key_value(
        logger,
        "Missing objects",
        len(missing_objects),
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    if missing_objects:
        logger.info("")
        logger.info(
            "Missing:"
        )

        for object_name in missing_objects:
            logger.info(
                "  %s",
                object_name,
            )

        return 1

    logger.info("")
    logger.info(
        "PIPELINE STATUS PASSED"
    )

    return 0


def run_cache_stage1(
    config: PipelineConfig,
    *,
    refresh_cache: bool,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "cache_stage1",
    )

    log_section(
        logger,
        "CACHE EXISTING STAGE 1 RAW PAGE TEXT",
        width=140,
    )

    raw_page_table = config.tables[
        "raw_pages"
    ]

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        connection,
        [
            raw_page_table,
        ],
    )

    quoted_table = quote_identifier(
        raw_page_table
    )

    raw_pages = connection.execute(
        f"""
        SELECT
            contract_number,
            district,
            source_file_name,
            source_file_path,
            page_number,
            raw_page_text,
            raw_page_text_hash

        FROM {quoted_table}

        ORDER BY
            contract_number,
            page_number
        """
    ).fetchdf()

    connection.close()

    log_key_value(
        logger,
        "Raw-page rows",
        f"{len(raw_pages):,}",
    )

    if raw_pages.empty:
        logger.info(
            "No raw-page rows were found."
        )

        return 1

    written_pages = 0
    skipped_pages = 0
    refreshed_pages = 0
    hash_mismatches = 0
    contracts_processed = 0

    for contract_number, contract_rows in (
        raw_pages.groupby(
            "contract_number",
            sort=True,
        )
    ):
        page_records: list[dict] = []

        for row in contract_rows.itertuples(
            index=False,
        ):
            page_number = int(
                row.page_number
            )

            text = (
                row.raw_page_text
                if row.raw_page_text
                is not None
                else ""
            )

            calculated_hash = text_sha256(
                text
            )

            stored_hash = (
                row.raw_page_text_hash
                if row.raw_page_text_hash
                is not None
                else ""
            )

            if (
                stored_hash
                and calculated_hash
                != stored_hash
            ):
                hash_mismatches += 1

            cache_path = (
                config.cache_directory
                / str(
                    config.target_year
                )
                / str(
                    contract_number
                )
                / (
                    f"page_"
                    f"{page_number:04d}.txt"
                )
            )

            file_existed = cache_path.exists()

            if (
                file_existed
                and not refresh_cache
            ):
                skipped_pages += 1

            else:
                write_cached_page(
                    config.cache_directory,
                    config.target_year,
                    str(contract_number),
                    page_number,
                    text,
                )

                if file_existed:
                    refreshed_pages += 1
                else:
                    written_pages += 1

            page_records.append(
                {
                    "page_number": (
                        page_number
                    ),
                    "cache_file": str(
                        cache_path.relative_to(
                            config.project_root
                        )
                    ),
                    "text_characters": (
                        len(text)
                    ),
                    "sha256": (
                        calculated_hash
                    ),
                    "stored_sha256": (
                        stored_hash
                    ),
                    "source_file_name": (
                        row.source_file_name
                    ),
                    "source_file_path": (
                        row.source_file_path
                    ),
                    "district": (
                        int(row.district)
                        if row.district
                        is not None
                        else None
                    ),
                }
            )

        write_contract_manifest(
            config.cache_directory,
            config.target_year,
            str(contract_number),
            page_records,
        )

        contracts_processed += 1

        logger.info(
            "%s | pages=%s",
            contract_number,
            len(page_records),
        )

    log_subsection(
        logger,
        "CACHE SUMMARY",
        width=140,
    )

    log_key_value(
        logger,
        "Contracts processed",
        contracts_processed,
    )

    log_key_value(
        logger,
        "Pages written",
        written_pages,
    )

    log_key_value(
        logger,
        "Existing pages skipped",
        skipped_pages,
    )

    log_key_value(
        logger,
        "Existing pages refreshed",
        refreshed_pages,
    )

    log_key_value(
        logger,
        "Hash mismatches",
        hash_mismatches,
    )

    log_key_value(
        logger,
        "Cache root",
        config.cache_directory,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    if hash_mismatches:
        logger.info("")
        logger.info(
            "CACHE VALIDATION FAILED"
        )

        return 1

    logger.info("")
    logger.info(
        "STAGE 1 CACHE PASSED"
    )

    return 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Caltrans subcontractor "
            "pipeline utilities."
        )
    )

    parser.add_argument(
        "--stage",
        required=True,
        choices=[
            "status",
            "cache-stage1",
        ],
        help=(
            "Pipeline stage or utility "
            "to execute."
        ),
    )

    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help=(
            "Overwrite existing cached "
            "page text."
        ),
    )

    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help=(
            "Optional alternate settings "
            "JSON file."
        ),
    )

    return parser.parse_args()



def pipeline_config_from_context(
    context: FrameworkContext,
) -> PipelineConfig:
    if context.target_year is None:
        raise RuntimeError(
            "Framework target_year is not configured."
        )

    return PipelineConfig(
        project_root=context.paths.project_root,
        database_path=context.paths.database,
        backup_directory=context.paths.backups,
        cache_directory=context.paths.cache,
        log_directory=context.paths.logs,
        target_year=context.target_year,
        target_districts=context.target_districts,
        tables=context.tables,
    )



def main() -> int:
    arguments = parse_arguments()

    context = FrameworkContext.load()
    config = pipeline_config_from_context(
        context
    )

    config.ensure_directories()

    if arguments.stage == "status":
        return run_status(
            config
        )

    if arguments.stage == "cache-stage1":
        return run_cache_stage1(
            config,
            refresh_cache=(
                arguments.refresh_cache
            ),
        )

    raise RuntimeError(
        f"Unsupported stage: "
        f"{arguments.stage}"
    )


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )

    except Exception as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )

        raise
