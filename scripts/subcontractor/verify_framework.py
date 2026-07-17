from __future__ import annotations

import compileall
from dataclasses import dataclass
from pathlib import Path

from scripts.subcontractor.config import PipelineConfig
from scripts.subcontractor.database import (
    connect_database,
    list_database_objects,
)
from scripts.subcontractor.logging_utils import (
    configure_logging,
    log_key_value,
    log_section,
    log_subsection,
)


PRODUCTION_MODULES = [
    "config.py",
    "database.py",
    "logging_utils.py",
    "pdf_cache.py",
    "validation.py",
    "run_pipeline.py",
    "stages/validate_stage1.py",
    "stages/stage2_alternate_parser.py",
    "stages/certify_alternate_stage2.py",
    "stages/build_identity_overlay.py",
    "stages/promote_alternate_disclosures.py",
]

DIAGNOSTIC_MODULES = [
    "stages/audit_bidder_context.py",
    "stages/parse_alternate_layout.py",
    "stages/group_alternate_layout.py",
    "stages/reconcile_alternate_blocks.py",
    "stages/audit_quarantined_contracts.py",
    "stages/audit_quarantine_context.py",
]


@dataclass(frozen=True)
class ModuleStatus:
    relative_path: str
    category: str
    exists: bool
    size_bytes: int


def inspect_modules(
    package_root: Path,
) -> list[ModuleStatus]:
    records: list[ModuleStatus] = []

    for category, module_paths in [
        ("PRODUCTION", PRODUCTION_MODULES),
        ("DIAGNOSTIC", DIAGNOSTIC_MODULES),
    ]:
        for relative_path in module_paths:
            full_path = (
                package_root
                / relative_path
            )

            records.append(
                ModuleStatus(
                    relative_path=relative_path,
                    category=category,
                    exists=full_path.exists(),
                    size_bytes=(
                        full_path.stat().st_size
                        if full_path.exists()
                        else 0
                    ),
                )
            )

    return records


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()

    logger, log_path = configure_logging(
        config.log_directory,
        "verify_framework",
    )

    log_section(
        logger,
        "SUBCONTRACTOR FRAMEWORK VERIFICATION",
        width=140,
    )

    package_root = (
        config.project_root
        / "scripts"
        / "subcontractor"
    )

    required_directories = [
        package_root,
        package_root / "stages",
        package_root / "tests",
        config.cache_directory,
        config.log_directory,
        config.backup_directory,
        (
            config.project_root
            / "data"
            / "reports"
            / "subcontractor"
        ),
    ]

    log_subsection(
        logger,
        "DIRECTORIES",
        width=140,
    )

    missing_directories: list[Path] = []

    for directory in required_directories:
        exists = directory.exists()

        logger.info(
            "%-100s %s",
            str(directory),
            "FOUND" if exists else "MISSING",
        )

        if not exists:
            missing_directories.append(
                directory
            )

    module_statuses = inspect_modules(
        package_root
    )

    log_subsection(
        logger,
        "MODULE INVENTORY",
        width=140,
    )

    logger.info(
        "%-12s %-70s %-10s %12s",
        "Category",
        "Module",
        "Status",
        "Bytes",
    )
    logger.info("-" * 110)

    missing_modules: list[str] = []

    for status in module_statuses:
        logger.info(
            "%-12s %-70s %-10s %12s",
            status.category,
            status.relative_path,
            (
                "FOUND"
                if status.exists
                else "MISSING"
            ),
            f"{status.size_bytes:,}",
        )

        if not status.exists:
            missing_modules.append(
                status.relative_path
            )

    log_subsection(
        logger,
        "PYTHON COMPILATION",
        width=140,
    )

    compile_passed = compileall.compile_dir(
        str(package_root),
        quiet=1,
        force=True,
    )

    log_key_value(
        logger,
        "Compile result",
        (
            "PASSED"
            if compile_passed
            else "FAILED"
        ),
    )

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    database_objects = (
        list_database_objects(
            connection
        )
    )

    connection.close()

    expected_database_objects = [
        *config.tables.values(),
        (
            "bid_tab_subcontractor_disclosure_"
            "2025_alt_stage2_v1"
        ),
        (
            "bid_tab_subcontractor_disclosure_"
            "2025_alt_stage2_v2"
        ),
        (
            "bid_tab_subcontractor_disclosure_"
            "2025_alt_certified_v1"
        ),
        (
            "bid_tab_subcontractor_alt_"
            "certification_audit_2025_v1"
        ),
        (
            "bid_tab_subcontractor_disclosure_"
            "2025_alt_identity_overlay_v1"
        ),
        (
            "bid_tab_subcontractor_alt_"
            "identity_audit_2025_v1"
        ),
        (
            "bid_tab_subcontractor_alt_"
            "identity_review_2025_v1"
        ),
        (
            "bid_tab_subcontractor_disclosure_"
            "2025_alt_promoted_v1"
        ),
        (
            "bid_tab_subcontractor_alt_"
            "promotion_audit_2025_v1"
        ),
    ]

    log_subsection(
        logger,
        "DATABASE OBJECTS",
        width=140,
    )

    missing_objects: list[str] = []

    for object_name in expected_database_objects:
        exists = (
            object_name
            in database_objects
        )

        logger.info(
            "%-105s %s",
            object_name,
            "FOUND" if exists else "MISSING",
        )

        if not exists:
            missing_objects.append(
                object_name
            )

    log_subsection(
        logger,
        "VERIFICATION SUMMARY",
        width=140,
    )

    log_key_value(
        logger,
        "Production modules",
        len(PRODUCTION_MODULES),
    )
    log_key_value(
        logger,
        "Diagnostic modules",
        len(DIAGNOSTIC_MODULES),
    )
    log_key_value(
        logger,
        "Missing directories",
        len(missing_directories),
    )
    log_key_value(
        logger,
        "Missing modules",
        len(missing_modules),
    )
    log_key_value(
        logger,
        "Missing database objects",
        len(missing_objects),
    )
    log_key_value(
        logger,
        "Database objects found",
        len(database_objects),
    )
    log_key_value(
        logger,
        "Log",
        log_path,
    )

    failed = (
        bool(missing_directories)
        or bool(missing_modules)
        or bool(missing_objects)
        or not compile_passed
    )

    logger.info("")

    if failed:
        logger.info(
            "SUBCONTRACTOR FRAMEWORK VERIFICATION FAILED"
        )
        return 1

    logger.info(
        "SUBCONTRACTOR FRAMEWORK VERIFICATION PASSED"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
