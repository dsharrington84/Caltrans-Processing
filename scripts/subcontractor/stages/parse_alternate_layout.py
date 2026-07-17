from __future__ import annotations

import re
from pathlib import Path

import duckdb
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


HISTORY_TABLE = (
    "historical_bid_prices_identity_enriched_v1"
)

FORM_HEADER_PATTERN = re.compile(
    r"BIDDER\s+ID.*?"
    r"NAME\s+AND\s+ADDRESS.*?"
    r"LICENSE\s+NUMBER.*?"
    r"DESCRIPTION\s+OF\s+PORTION\s+OF\s+WORK\s+SUBCONTRACTED",
    re.IGNORECASE | re.DOTALL,
)

VC_PATTERN = re.compile(
    r"\bVC[0-9A-Z]{8,14}\b",
    re.IGNORECASE,
)

MONEY_PATTERN = re.compile(
    r"\$?\s*\d[\d,]*(?:\.\d{2})?"
)

PERCENT_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*%"
)


def normalize_vc_id(
    value: str,
) -> str:
    value = re.sub(
        r"[^A-Z0-9]",
        "",
        str(value).upper(),
    )

    if value.startswith("VCO"):
        value = "VC0" + value[3:]

    return value


def compact_text(
    value: str,
    *,
    limit: int = 500,
) -> str:
    value = re.sub(
        r"[ \t]+",
        " ",
        value or "",
    )

    value = re.sub(
        r"\n{3,}",
        "\n\n",
        value,
    ).strip()

    if len(value) <= limit:
        return value

    return value[: limit - 3] + "..."


def build_identity_lookup(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, dict]:
    frame = connection.execute(
        f"""
        SELECT
            bidder_id,
            bidder_name,
            COUNT(DISTINCT contract_number)
                AS contract_count,
            COUNT(*) AS source_rows

        FROM {HISTORY_TABLE}

        WHERE bidder_id IS NOT NULL
          AND bidder_name IS NOT NULL
          AND TRIM(bidder_id) <> ''
          AND TRIM(bidder_name) <> ''

        GROUP BY
            bidder_id,
            bidder_name
        """
    ).fetchdf()

    if frame.empty:
        return {}

    frame["normalized_bidder_id"] = (
        frame["bidder_id"]
        .astype(str)
        .map(normalize_vc_id)
    )

    frame = (
        frame.sort_values(
            [
                "normalized_bidder_id",
                "contract_count",
                "source_rows",
                "bidder_name",
            ],
            ascending=[
                True,
                False,
                False,
                True,
            ],
        )
        .drop_duplicates(
            subset=["normalized_bidder_id"],
            keep="first",
        )
    )

    return {
        row.normalized_bidder_id: {
            "bidder_name": row.bidder_name,
            "identity_contract_count": int(
                row.contract_count
            ),
        }
        for row in frame.itertuples(
            index=False
        )
    }


def detect_status_column(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> str:
    columns = set(
        connection.execute(
            """
            SELECT column_name

            FROM information_schema.columns

            WHERE table_name = ?
            """,
            [table_name],
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
            if column in columns
        ),
        None,
    )

    if status_column is None:
        raise RuntimeError(
            "No recognized Stage 1 status column."
        )

    return status_column


def extract_page_candidate(
    contract_number: str,
    page_number: int,
    raw_text: str,
    identity_lookup: dict[str, dict],
) -> dict:
    text = raw_text or ""

    header_found = bool(
        FORM_HEADER_PATTERN.search(text)
    )

    vc_matches = [
        normalize_vc_id(match)
        for match in VC_PATTERN.findall(text)
    ]

    unique_vc_ids = list(
        dict.fromkeys(vc_matches)
    )

    candidate_bidder_id = (
        unique_vc_ids[0]
        if unique_vc_ids
        else None
    )

    identity = identity_lookup.get(
        candidate_bidder_id or "",
        {},
    )

    lines = [
        line.rstrip()
        for line in text.splitlines()
    ]

    nonempty_lines = [
        line.strip()
        for line in lines
        if line.strip()
    ]

    candidate_line_number = None
    candidate_line = ""

    if candidate_bidder_id:
        for index, line in enumerate(
            lines,
            start=1,
        ):
            normalized_line = (
                normalize_vc_id(line)
            )

            if candidate_bidder_id in normalized_line:
                candidate_line_number = index
                candidate_line = line.strip()
                break

    money_values = [
        match.group(0).strip()
        for match in MONEY_PATTERN.finditer(text)
    ]

    percent_values = [
        match.group(0).strip()
        for match in PERCENT_PATTERN.finditer(text)
    ]

    return {
        "contract_number": contract_number,
        "page_number": page_number,
        "form_header_found": header_found,
        "vc_id_count": len(unique_vc_ids),
        "all_vc_ids": ", ".join(unique_vc_ids),
        "candidate_bidder_id": candidate_bidder_id,
        "candidate_bidder_name": identity.get(
            "bidder_name"
        ),
        "identity_contract_count": identity.get(
            "identity_contract_count",
            0,
        ),
        "candidate_line_number": candidate_line_number,
        "candidate_line": compact_text(
            candidate_line,
            limit=300,
        ),
        "nonempty_line_count": len(
            nonempty_lines
        ),
        "money_value_count": len(
            money_values
        ),
        "percent_value_count": len(
            percent_values
        ),
        "page_text_preview": compact_text(
            "\n".join(nonempty_lines),
            limit=900,
        ),
    }


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "parse_alternate_layout",
    )

    log_section(
        logger,
        "ALTERNATE-LAYOUT BIDDER FORM PARSER",
        width=160,
    )

    raw_pages_table = config.tables[
        "raw_pages"
    ]

    stage1_audit_table = config.tables[
        "stage1_audit"
    ]

    connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        connection,
        [
            raw_pages_table,
            stage1_audit_table,
            HISTORY_TABLE,
        ],
    )

    identity_lookup = build_identity_lookup(
        connection
    )

    status_column = detect_status_column(
        connection,
        stage1_audit_table,
    )

    raw_q = quote_identifier(
        raw_pages_table
    )

    audit_q = quote_identifier(
        stage1_audit_table
    )

    status_q = quote_identifier(
        status_column
    )

    review_contracts = connection.execute(
        f"""
        SELECT DISTINCT
            contract_number

        FROM {audit_q}

        WHERE {status_q}
            = 'REVIEW_REQUIRED'

        ORDER BY
            contract_number
        """
    ).fetchdf()["contract_number"].tolist()

    records: list[dict] = []

    for contract_number in review_contracts:
        pages = connection.execute(
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

        for row in pages.itertuples(
            index=False,
        ):
            candidate = extract_page_candidate(
                contract_number,
                int(row.page_number),
                row.raw_page_text or "",
                identity_lookup,
            )

            if (
                candidate["form_header_found"]
                or candidate["candidate_bidder_id"]
            ):
                records.append(
                    candidate
                )

    connection.close()

    frame = pd.DataFrame(
        records
    )

    output_directory = (
        config.project_root
        / "data"
        / "reports"
        / "subcontractor"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_directory
        / (
            "alternate_layout_bidder_candidates_"
            f"{config.target_year}.csv"
        )
    )

    frame.to_csv(
        output_path,
        index=False,
    )

    log_key_value(
        logger,
        "Review contracts",
        len(review_contracts),
    )

    log_key_value(
        logger,
        "Candidate form pages",
        len(frame),
    )

    if frame.empty:
        logger.info("")
        logger.info(
            "No alternate-layout forms detected."
        )
        return 1

    log_subsection(
        logger,
        "CONTRACT SUMMARY",
        width=160,
    )

    summary = (
        frame.groupby(
            "contract_number",
            as_index=False,
        )
        .agg(
            candidate_pages=(
                "page_number",
                "count",
            ),
            unique_candidate_ids=(
                "candidate_bidder_id",
                "nunique",
            ),
            known_identities=(
                "candidate_bidder_name",
                lambda values: values.notna().sum(),
            ),
            header_pages=(
                "form_header_found",
                "sum",
            ),
            multi_id_pages=(
                "vc_id_count",
                lambda values: int(
                    (values > 1).sum()
                ),
            ),
        )
    )

    logger.info(
        "%-13s %10s %11s %11s %10s %12s",
        "Contract",
        "Pages",
        "Unique IDs",
        "Known IDs",
        "Headers",
        "Multi-ID",
    )

    logger.info("-" * 80)

    for row in summary.itertuples(
        index=False,
    ):
        logger.info(
            "%-13s %10d %11d %11d %10d %12d",
            row.contract_number,
            row.candidate_pages,
            row.unique_candidate_ids,
            row.known_identities,
            row.header_pages,
            row.multi_id_pages,
        )

    duplicate_candidates = int(
        frame.duplicated(
            subset=[
                "contract_number",
                "candidate_bidder_id",
            ],
            keep=False,
        ).sum()
    )

    missing_candidate_ids = int(
        frame["candidate_bidder_id"]
        .isna()
        .sum()
    )

    unknown_identities = int(
        (
            frame["candidate_bidder_id"].notna()
            & frame["candidate_bidder_name"].isna()
        ).sum()
    )

    multi_id_pages = int(
        (
            frame["vc_id_count"] > 1
        ).sum()
    )

    log_subsection(
        logger,
        "PARSER SUMMARY",
        width=160,
    )

    log_key_value(
        logger,
        "Candidate pages",
        len(frame),
    )

    log_key_value(
        logger,
        "Missing candidate IDs",
        missing_candidate_ids,
    )

    log_key_value(
        logger,
        "Unknown bidder identities",
        unknown_identities,
    )

    log_key_value(
        logger,
        "Rows in duplicate candidate groups",
        duplicate_candidates,
    )

    log_key_value(
        logger,
        "Pages containing multiple VC IDs",
        multi_id_pages,
    )

    log_key_value(
        logger,
        "Diagnostic CSV",
        output_path,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    logger.info("")

    if missing_candidate_ids:
        logger.info(
            "ALTERNATE-LAYOUT PARSER REVIEW REQUIRED"
        )
        return 1

    logger.info(
        "ALTERNATE-LAYOUT PARSER AUDIT PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
