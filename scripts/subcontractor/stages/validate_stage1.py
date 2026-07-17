from __future__ import annotations

import logging

from scripts.subcontractor.config import PipelineConfig
from scripts.subcontractor.database import (
    connect_database,
    require_objects,
)
from scripts.subcontractor.logging_utils import (
    configure_logging,
    log_key_value,
    log_section,
    log_subsection,
)
from scripts.subcontractor.validation import (
    ValidationResult,
    all_passed,
    validate_child_contracts_in_parent,
    validate_contract_set_match,
    validate_no_nulls,
    validate_required_columns,
    validate_status_counts,
    validate_unique_key,
)


def print_validation_results(
    logger: logging.Logger,
    results: list[ValidationResult],
) -> None:
    logger.info(
        "%-72s %-8s %-12s %s",
        "Check",
        "Status",
        "Observed",
        "Detail",
    )
    logger.info("-" * 140)

    for result in results:
        logger.info(
            "%-72s %-8s %-12s %s",
            result.check_name[:72],
            "PASS" if result.passed else "FAIL",
            str(result.observed_value)[:12],
            result.detail,
        )


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "validate_stage1",
    )

    log_section(
        logger,
        "STAGE 1 VALIDATION",
        width=140,
    )

    manifest = config.tables["manifest"]
    preflight = config.tables["preflight"]
    parse_plan = config.tables["parse_plan"]
    page_audit = config.tables["page_audit"]
    raw_pages = config.tables["raw_pages"]
    bidder_sections = config.tables["bidder_sections"]
    disclosure_lines = config.tables["disclosure_lines"]
    rejected_lines = config.tables["rejected_lines"]
    stage1_audit = config.tables["stage1_audit"]

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        connection,
        config.tables.values(),
    )

    results: list[ValidationResult] = []

    required_columns = {
        manifest: ["contract_number"],
        preflight: ["contract_number"],
        parse_plan: ["contract_number"],
        page_audit: [
            "contract_number",
            "page_number",
        ],
        raw_pages: [
            "contract_number",
            "page_number",
            "raw_page_text",
        ],
        bidder_sections: ["contract_number"],
        disclosure_lines: ["contract_number"],
        rejected_lines: ["contract_number"],
        stage1_audit: ["contract_number"],
    }

    for table_name, columns in required_columns.items():
        results.append(
            validate_required_columns(
                connection,
                table_name,
                columns,
            )
        )

    results.extend(
        validate_no_nulls(
            connection,
            manifest,
            ["contract_number"],
        )
    )

    results.extend(
        validate_no_nulls(
            connection,
            raw_pages,
            [
                "contract_number",
                "page_number",
            ],
        )
    )

    for table_name in [
        manifest,
        preflight,
        parse_plan,
        stage1_audit,
    ]:
        results.append(
            validate_unique_key(
                connection,
                table_name,
                ["contract_number"],
            )
        )

    results.append(
        validate_unique_key(
            connection,
            raw_pages,
            [
                "contract_number",
                "page_number",
            ],
        )
    )

    for table_name in [
        preflight,
        parse_plan,
        stage1_audit,
    ]:
        results.append(
            validate_contract_set_match(
                connection,
                manifest,
                table_name,
            )
        )

    for child_table in [
        page_audit,
        raw_pages,
        bidder_sections,
        disclosure_lines,
        rejected_lines,
    ]:
        results.append(
            validate_child_contracts_in_parent(
                connection,
                manifest,
                child_table,
            )
        )

    log_subsection(
        logger,
        "VALIDATION CHECKS",
        width=140,
    )

    print_validation_results(
        logger,
        results,
    )

    log_subsection(
        logger,
        "STAGE 1 AUDIT STATUS COUNTS",
        width=140,
    )

    stage1_columns = set(
        connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = ?
            """,
            [stage1_audit],
        ).fetchdf()["column_name"]
    )

    status_column = next(
        (
            column
            for column in [
                "stage1_status",
                "parse_status",
                "audit_status",
                "status",
            ]
            if column in stage1_columns
        ),
        None,
    )

    if status_column is None:
        logger.info(
            "No recognized status column found."
        )
    else:
        status_counts = validate_status_counts(
            connection,
            stage1_audit,
            status_column,
        )

        for status_value, row_count in status_counts.items():
            log_key_value(
                logger,
                status_value,
                f"{row_count:,}",
            )

    connection.close()

    failed = [
        result
        for result in results
        if not result.passed
    ]

    log_subsection(
        logger,
        "VALIDATION SUMMARY",
        width=140,
    )

    log_key_value(
        logger,
        "Checks run",
        len(results),
    )
    log_key_value(
        logger,
        "Checks passed",
        len(results) - len(failed),
    )
    log_key_value(
        logger,
        "Checks failed",
        len(failed),
    )
    log_key_value(
        logger,
        "Log",
        log_path,
    )

    if not all_passed(results):
        logger.info("")
        logger.info(
            "STAGE 1 VALIDATION FAILED"
        )
        return 1

    logger.info("")
    logger.info(
        "STAGE 1 VALIDATION PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
