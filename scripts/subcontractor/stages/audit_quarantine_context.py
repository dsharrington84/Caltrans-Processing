from __future__ import annotations

import re

import pandas as pd

from scripts.subcontractor.config import PipelineConfig
from scripts.subcontractor.database import (
    connect_database,
    quote_identifier,
    require_objects,
)
from scripts.subcontractor.logging_utils import (
    configure_logging,
    log_key_value,
    log_section,
    log_subsection,
)
from scripts.subcontractor.pdf_cache import (
    get_or_extract_page,
)


MANIFEST_TABLE_KEY = "manifest"

STATUS_PATTERNS = {
    "NO_SUBCONTRACTORS": re.compile(
        r"\b("
        r"NO\s+SUBCONTRACTORS?"
        r"|NONE\s+LISTED"
        r"|NO\s+SUBCONTRACTOR\s+DISCLOSURE"
        r"|NO\s+SUBCONTRACTING"
        r")\b",
        re.IGNORECASE,
    ),
    "WITHDRAWN": re.compile(
        r"\bWITHDRAWN\b",
        re.IGNORECASE,
    ),
    "REJECTED": re.compile(
        r"\b("
        r"REJECTED"
        r"|NON[-\s]?RESPONSIVE"
        r"|DISQUALIFIED"
        r")\b",
        re.IGNORECASE,
    ),
    "PREFERENCE_INELIGIBLE": re.compile(
        r"\b("
        r"PREFERENCE\s+NOT\s+MET"
        r"|PREFERENCE\s+INELIGIBLE"
        r"|SMALL\s+BUSINESS\s+PREFERENCE"
        r")\b",
        re.IGNORECASE,
    ),
    "BIDDER_SUMMARY": re.compile(
        r"\b("
        r"BIDDER\s+SUMMARY"
        r"|BID\s+RESULTS?"
        r"|LIST\s+OF\s+BIDDERS?"
        r"|BIDDER\s+INFORMATION"
        r"|BID\s+SUMMARY"
        r")\b",
        re.IGNORECASE,
    ),
    "RANK_SIGNAL": re.compile(
        r"\b("
        r"RANK"
        r"|LOW\s+BIDDER"
        r"|APPARENT\s+LOW"
        r"|BID\s+AMOUNT"
        r")\b",
        re.IGNORECASE,
    ),
}


OUTPUT_COLUMNS = [
    "contract_number",
    "page_number",
    "relative_location",
    "signals",
    "vc_ids",
    "line_count",
    "first_30_lines",
    "text_preview",
    "source_file_path",
    "cache_path",
    "cache_hit",
]


def compact(
    value: str,
    limit: int = 320,
) -> str:
    value = re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()

    if len(value) <= limit:
        return value

    return value[: limit - 3] + "..."


def detect_signals(
    text: str,
) -> list[str]:
    return [
        label
        for label, pattern
        in STATUS_PATTERNS.items()
        if pattern.search(text or "")
    ]


def resolve_manifest_columns(
    connection,
    manifest_table: str,
) -> tuple[str, str]:
    columns = set(
        connection.execute(
            """
            SELECT column_name

            FROM information_schema.columns

            WHERE table_name = ?
            """,
            [manifest_table],
        ).fetchdf()["column_name"].tolist()
    )

    contract_column = next(
        (
            column
            for column in [
                "contract_number",
                "contract_no",
                "contract",
            ]
            if column in columns
        ),
        None,
    )

    path_column = next(
        (
            column
            for column in [
                "selected_source_file_path",
                "source_file_path",
                "file_path",
                "pdf_path",
                "selected_file_path",
            ]
            if column in columns
        ),
        None,
    )

    if contract_column is None:
        raise RuntimeError(
            "Could not identify the manifest "
            "contract-number column."
        )

    if path_column is None:
        raise RuntimeError(
            "Could not identify a source PDF path "
            "column in the manifest."
        )

    return contract_column, path_column


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "audit_quarantine_context",
    )

    log_section(
        logger,
        "QUARANTINED CONTRACT PDF-CONTEXT AUDIT",
        width=180,
    )

    report_directory = (
        config.project_root
        / "data"
        / "reports"
        / "subcontractor"
    )

    block_path = (
        report_directory
        / (
            "quarantined_bidder_block_audit_"
            f"{config.target_year}.csv"
        )
    )

    case_path = (
        report_directory
        / (
            "quarantined_contract_case_audit_"
            f"{config.target_year}.csv"
        )
    )

    if not block_path.exists():
        raise FileNotFoundError(
            f"Block audit not found: {block_path}"
        )

    if not case_path.exists():
        raise FileNotFoundError(
            f"Contract case audit not found: {case_path}"
        )

    blocks = pd.read_csv(
        block_path,
        dtype={
            "contract_number": str,
            "bidder_id": str,
        },
    )

    cases = pd.read_csv(
        case_path,
        dtype={
            "contract_number": str,
        },
    )

    contracts = (
        cases["contract_number"]
        .drop_duplicates()
        .tolist()
    )

    manifest_table = config.tables[
        MANIFEST_TABLE_KEY
    ]

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        connection,
        [manifest_table],
    )

    (
        contract_column,
        path_column,
    ) = resolve_manifest_columns(
        connection,
        manifest_table,
    )

    manifest_q = quote_identifier(
        manifest_table
    )

    contract_q = quote_identifier(
        contract_column
    )

    path_q = quote_identifier(
        path_column
    )

    placeholders = ", ".join(
        ["?"] * len(contracts)
    )

    manifest = connection.execute(
        f"""
        SELECT
            CAST(
                {contract_q}
                AS VARCHAR
            ) AS contract_number,
            CAST(
                {path_q}
                AS VARCHAR
            ) AS source_file_path

        FROM {manifest_q}

        WHERE CAST(
            {contract_q}
            AS VARCHAR
        ) IN (
            {placeholders}
        )

        ORDER BY
            contract_number
        """,
        contracts,
    ).fetchdf()

    connection.close()

    source_lookup = {}

    for row in manifest.itertuples(
        index=False
    ):
        if pd.isna(
            row.source_file_path
        ):
            continue

        source_path = Path(
            str(row.source_file_path)
        ).expanduser()

        if not source_path.is_absolute():
            source_path = (
                config.project_root
                / source_path
            )

        source_lookup[
            str(row.contract_number)
        ] = source_path.resolve()

    missing_sources = [
        contract
        for contract in contracts
        if contract not in source_lookup
        or not source_lookup[
            contract
        ].exists()
    ]

    if missing_sources:
        raise RuntimeError(
            "Missing source PDFs for: "
            + ", ".join(
                missing_sources
            )
        )

    records: list[dict] = []

    extracted_pages = 0
    cache_hits = 0

    for contract_number in contracts:
        contract_blocks = (
            blocks[
                blocks["contract_number"]
                == contract_number
            ]
            .sort_values(
                "block_sequence"
            )
        )

        if contract_blocks.empty:
            continue

        first_block_page = int(
            contract_blocks[
                "first_page"
            ].min()
        )

        last_block_page = int(
            contract_blocks[
                "last_page"
            ].max()
        )

        context_pages: set[int] = set()

        # Capture the PDF pages leading into the
        # disclosure sequence. These are most likely
        # to contain bidder summaries and status notes.
        for page_number in range(
            max(
                1,
                first_block_page - 10,
            ),
            first_block_page,
        ):
            context_pages.add(
                page_number
            )

        ordered_blocks = list(
            contract_blocks.itertuples(
                index=False,
            )
        )

        # Capture gaps between disclosure blocks.
        for previous, current in zip(
            ordered_blocks,
            ordered_blocks[1:],
        ):
            for page_number in range(
                int(previous.last_page) + 1,
                int(current.first_page),
            ):
                context_pages.add(
                    page_number
                )

        # Capture pages immediately after the last block.
        for page_number in range(
            last_block_page + 1,
            last_block_page + 4,
        ):
            context_pages.add(
                page_number
            )

        source_pdf = source_lookup[
            contract_number
        ]

        for page_number in sorted(
            context_pages
        ):
            try:
                (
                    text,
                    cache_path,
                    cache_hit,
                ) = get_or_extract_page(
                    config.cache_directory,
                    config.target_year,
                    contract_number,
                    source_pdf,
                    page_number,
                )
            except RuntimeError as error:
                message = str(error).lower()

                # Ignore attempts past the end of a PDF.
                if (
                    "wrong page range" in message
                    or "page" in message
                    and "range" in message
                ):
                    continue

                raise

            extracted_pages += 1

            if cache_hit:
                cache_hits += 1

            nonempty_lines = [
                line.rstrip()
                for line in text.splitlines()
                if line.strip()
            ]

            signals = detect_signals(
                text
            )

            vc_ids = sorted(
                {
                    value.upper()
                    for value in re.findall(
                        r"\bVC[0-9A-Z]{8,14}\b",
                        text,
                        flags=re.IGNORECASE,
                    )
                }
            )

            relative_location = (
                "BEFORE_BLOCKS"
                if page_number
                < first_block_page
                else (
                    "AFTER_BLOCKS"
                    if page_number
                    > last_block_page
                    else "BETWEEN_BLOCKS"
                )
            )

            records.append(
                {
                    "contract_number": (
                        contract_number
                    ),
                    "page_number": (
                        page_number
                    ),
                    "relative_location": (
                        relative_location
                    ),
                    "signals": (
                        "|".join(signals)
                    ),
                    "vc_ids": (
                        ", ".join(vc_ids)
                    ),
                    "line_count": (
                        len(nonempty_lines)
                    ),
                    "first_30_lines": (
                        "\n".join(
                            nonempty_lines[:30]
                        )
                    ),
                    "text_preview": compact(
                        " | ".join(
                            nonempty_lines[:35]
                        )
                    ),
                    "source_file_path": str(
                        source_pdf
                    ),
                    "cache_path": str(
                        cache_path
                    ),
                    "cache_hit": (
                        cache_hit
                    ),
                }
            )

    # Always write headers, even if no records are found.
    context = pd.DataFrame(
        records,
        columns=OUTPUT_COLUMNS,
    )

    output_path = (
        report_directory
        / (
            "quarantined_page_context_"
            f"{config.target_year}.csv"
        )
    )

    context.to_csv(
        output_path,
        index=False,
    )

    log_key_value(
        logger,
        "Contracts audited",
        len(contracts),
    )

    log_key_value(
        logger,
        "Context pages extracted",
        extracted_pages,
    )

    log_key_value(
        logger,
        "Cache hits",
        cache_hits,
    )

    log_key_value(
        logger,
        "Context rows written",
        len(context),
    )

    log_subsection(
        logger,
        "CONTEXT PAGE SIGNALS",
        width=180,
    )

    if context.empty:
        logger.info(
            "No context pages could be extracted."
        )
    else:
        logger.info(
            "%-13s %6s %-17s %-50s %-35s %s",
            "Contract",
            "Page",
            "Location",
            "Signals",
            "VC IDs",
            "Preview",
        )

        logger.info("-" * 180)

        for row in context.itertuples(
            index=False,
        ):
            logger.info(
                "%-13s %6d %-17s %-50s %-35s %s",
                row.contract_number,
                int(row.page_number),
                row.relative_location,
                str(row.signals)[:50],
                str(row.vc_ids)[:35],
                row.text_preview[:60],
            )

    log_subsection(
        logger,
        "SIGNAL SUMMARY",
        width=180,
    )

    if context.empty:
        logger.info(
            "No signals available."
        )
    else:
        exploded_signals = (
            context["signals"]
            .fillna("")
            .str.split("|")
            .explode()
        )

        exploded_signals = (
            exploded_signals[
                exploded_signals != ""
            ]
        )

        if exploded_signals.empty:
            logger.info(
                "No recognized status signals found."
            )
        else:
            for signal, count in (
                exploded_signals
                .value_counts()
                .items()
            ):
                log_key_value(
                    logger,
                    signal,
                    int(count),
                )

    log_key_value(
        logger,
        "Context CSV",
        output_path,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    logger.info("")
    logger.info(
        "QUARANTINED PDF-CONTEXT AUDIT PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
