from __future__ import annotations

import re

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


VC_PATTERN = re.compile(
    r"\bVC[0-9A-Z]{8,14}\b",
    re.IGNORECASE,
)

BIDDER_HEADER_PATTERNS = [
    re.compile(
        r"\bBIDDER(?:'S)?\s+NAME\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bPRIME\s+CONTRACTOR\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bCONTRACTOR(?:'S)?\s+NAME\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bBIDDER\s+NO\.?\b",
        re.IGNORECASE,
    ),
]


def compact_text(
    value: str,
    *,
    limit: int = 180,
) -> str:
    text = re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()

    if len(text) <= limit:
        return text

    return text[: limit - 3] + "..."


def detect_header_signal(
    text: str,
) -> bool:
    return any(
        pattern.search(text or "")
        for pattern in BIDDER_HEADER_PATTERNS
    )


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "audit_bidder_context",
    )

    log_section(
        logger,
        "BIDDER CONTEXT RECOVERY AUDIT",
        width=150,
    )

    stage1_audit = config.tables[
        "stage1_audit"
    ]
    raw_pages = config.tables[
        "raw_pages"
    ]
    bidder_sections = config.tables[
        "bidder_sections"
    ]
    disclosure_lines = config.tables[
        "disclosure_lines"
    ]

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        connection,
        [
            stage1_audit,
            raw_pages,
            bidder_sections,
            disclosure_lines,
        ],
    )

    stage1_q = quote_identifier(
        stage1_audit
    )
    raw_q = quote_identifier(
        raw_pages
    )
    bidder_q = quote_identifier(
        bidder_sections
    )
    disclosure_q = quote_identifier(
        disclosure_lines
    )

    audit_columns = set(
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
            if column in audit_columns
        ),
        None,
    )

    if status_column is None:
        raise RuntimeError(
            "No recognized Stage 1 status column found."
        )

    status_q = quote_identifier(
        status_column
    )

    review_contracts = connection.execute(
        f"""
        SELECT DISTINCT
            contract_number

        FROM {stage1_q}

        WHERE {status_q} = 'REVIEW_REQUIRED'

        ORDER BY
            contract_number
        """
    ).fetchdf()

    log_key_value(
        logger,
        "Review contracts",
        len(review_contracts),
    )

    if review_contracts.empty:
        logger.info("")
        logger.info(
            "NO BIDDER CONTEXT RECOVERY REQUIRED"
        )
        connection.close()
        return 0

    summary_rows: list[dict] = []

    for contract_number in review_contracts[
        "contract_number"
    ].tolist():
        raw_frame = connection.execute(
            f"""
            SELECT
                page_number,
                raw_page_text

            FROM {raw_q}

            WHERE contract_number = ?

            ORDER BY
                page_number
            """,
            [contract_number],
        ).fetchdf()

        bidder_count = int(
            connection.execute(
                f"""
                SELECT COUNT(*)

                FROM {bidder_q}

                WHERE contract_number = ?
                """,
                [contract_number],
            ).fetchone()[0]
        )

        disclosure_count = int(
            connection.execute(
                f"""
                SELECT COUNT(*)

                FROM {disclosure_q}

                WHERE contract_number = ?
                """,
                [contract_number],
            ).fetchone()[0]
        )

        all_vc_ids: set[str] = set()
        header_pages: list[int] = []
        sample_lines: list[str] = []

        for row in raw_frame.itertuples(
            index=False,
        ):
            page_number = int(
                row.page_number
            )
            text = row.raw_page_text or ""

            for match in VC_PATTERN.findall(
                text
            ):
                all_vc_ids.add(
                    match.upper().replace(
                        "VCO",
                        "VC0",
                    )
                )

            if detect_header_signal(
                text
            ):
                header_pages.append(
                    page_number
                )

                if len(sample_lines) < 3:
                    for line in text.splitlines():
                        if detect_header_signal(
                            line
                        ):
                            sample_lines.append(
                                compact_text(line)
                            )

                            if len(sample_lines) >= 3:
                                break

        summary_rows.append(
            {
                "contract_number": contract_number,
                "raw_pages": len(raw_frame),
                "bidder_sections": bidder_count,
                "disclosure_lines": disclosure_count,
                "vc_ids_found": len(all_vc_ids),
                "header_pages": len(
                    set(header_pages)
                ),
                "candidate_vc_ids": ", ".join(
                    sorted(all_vc_ids)[:8]
                ),
                "sample_header": (
                    sample_lines[0]
                    if sample_lines
                    else ""
                ),
            }
        )

    log_subsection(
        logger,
        "RECOVERY SIGNALS",
        width=150,
    )

    logger.info(
        "%-13s %8s %9s %11s %8s %10s %-36s %s",
        "Contract",
        "Pages",
        "Sections",
        "Disc lines",
        "VC IDs",
        "Hdr pages",
        "Candidate VC IDs",
        "Sample header",
    )
    logger.info("-" * 150)

    for row in summary_rows:
        logger.info(
            "%-13s %8s %9s %11s %8s %10s %-36s %s",
            row["contract_number"],
            row["raw_pages"],
            row["bidder_sections"],
            row["disclosure_lines"],
            row["vc_ids_found"],
            row["header_pages"],
            row["candidate_vc_ids"][:36],
            row["sample_header"][:55],
        )

    contracts_with_vc_ids = sum(
        row["vc_ids_found"] > 0
        for row in summary_rows
    )

    contracts_with_headers = sum(
        row["header_pages"] > 0
        for row in summary_rows
    )

    contracts_with_disclosures = sum(
        row["disclosure_lines"] > 0
        for row in summary_rows
    )

    log_subsection(
        logger,
        "AUDIT SUMMARY",
        width=150,
    )

    log_key_value(
        logger,
        "Contracts reviewed",
        len(summary_rows),
    )
    log_key_value(
        logger,
        "Contracts with VC IDs in text",
        contracts_with_vc_ids,
    )
    log_key_value(
        logger,
        "Contracts with bidder-header signals",
        contracts_with_headers,
    )
    log_key_value(
        logger,
        "Contracts with disclosure lines",
        contracts_with_disclosures,
    )
    log_key_value(
        logger,
        "Log",
        log_path,
    )

    logger.info("")
    logger.info(
        "BIDDER CONTEXT AUDIT PASSED"
    )

    connection.close()
    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
