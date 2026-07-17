from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd

from scripts.subcontractor.config import PipelineConfig
from scripts.subcontractor.database import (
    connect_database,
    create_backup,
    ensure_target_objects_absent,
    quote_identifier,
    require_objects,
)
from scripts.subcontractor.logging_utils import (
    configure_logging,
    log_key_value,
    log_section,
    log_subsection,
)


TARGET_TABLE = (
    "bid_tab_subcontractor_disclosure_"
    "2025_alt_stage2_v2"
)

HISTORY_TABLE = (
    "historical_bid_prices_identity_enriched_v1"
)

WORK_MARKER_PATTERN = re.compile(
    r"""
    \b(
        ITEMS?
        |CONSTRUCTION\s+AREA\s+SIGNS?
        |TRAFFIC\s+CONTROL
        |STATIONARY\s+IMPACT
        |PORTABLE\s+RADAR
        |AUTOMATED\s+FLAGGER
        |PAVEMENT\s+MARKER
        |THERMOPLASTIC
        |TRAFFIC\s+STRIPE\s+TAPE
        |CONTRAST\s+STRIPE
        |REMOVE\s+TRAFFIC
        |MOBILIZATION
        |MOBILE\s+BARRIER
        |TEMP(?:ORARY)?\.?\s+
        |TREATED\s+WOOD
        |GUARD\s*RAIL
        |MIDWEST\s+GUARDRAIL
        |SALVAGE\s+END
        |HIGH\s+FRICTION
        |COLD\s+PLANE
        |GRIND\s+EXISTING
        |HOT\s+MIX
        |TACK\s+COAT
        |LEAN\s+CONCRETE
        |DRILL\s+AND\s+BOND
        |INDIVIDUAL\s+SLAB
        |OPERATED\s+EQUIPMENT
        |TRUCKING
        |CLEARING\s+AND\s+GRUBBING
        |VEGETATION\s+CONTROL
        |BONDED\s+FIBER
        |COMPOST
        |INCORPORATE\s+MATERIALS
        |LEAD\s+COMPLIANCE
        |CONTRACTOR-SUPPLIED
        |FOG\s+SEAL
        |RUMBLE\s+STRIP
        |MAINTAINING\s+EXISTING
        |MODIFYING\s+FIBER
        |PARTIAL\s+TRAFFIC
        |PLACE\s+HOT
        |PLACE\s+HMA
        |LCP
        |MOB
        |CAS
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

ITEM_PATTERN = re.compile(
    r"\bITEMS?\s+([0-9A-Z,\-&\s]+)",
    re.IGNORECASE,
)

PERCENT_PATTERN = re.compile(
    r"\((\d+(?:\.\d+)?)\s*%\)",
    re.IGNORECASE,
)

ADDRESS_PATTERN = re.compile(
    r"""
    ^
    (?P<city>.+?)
    \s+
    (?P<state>[A-Z]{2})
    \s+
    (?P<license>
        \d{4,8}[A-Z]?
        |N/?A
        |ABSENT
    )
    (?P<trailing>.*)
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize_space(
    value: object,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        "" if value is None else str(value),
    ).strip()


def normalize_vc_id(
    value: object,
) -> str:
    normalized = re.sub(
        r"[^A-Z0-9]",
        "",
        normalize_space(value).upper(),
    )

    if normalized.startswith("VCO"):
        normalized = "VC0" + normalized[3:]

    return normalized


def normalize_license(
    value: object,
) -> str:
    value = normalize_space(value).upper()

    if value in {
        "NA",
        "N/A",
        "ABSENT",
    }:
        return value

    return re.sub(
        r"[^A-Z0-9]",
        "",
        value,
    )


def longest_common_token_prefix(
    values: list[str],
) -> str:
    token_lists = [
        normalize_space(value).split()
        for value in values
        if normalize_space(value)
    ]

    if not token_lists:
        return ""

    prefix: list[str] = []

    for tokens in zip(*token_lists):
        normalized_tokens = {
            token.upper().strip(".,;:")
            for token in tokens
        }

        if len(normalized_tokens) != 1:
            break

        prefix.append(tokens[0])

    return " ".join(prefix).strip(
        " ,.;:-"
    )


def clean_name_candidate(
    value: str,
) -> str:
    value = normalize_space(value)

    value = re.sub(
        r"\bITEMS?\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = value.strip(
        " ,.;:-"
    )

    return value


def split_name_and_description_by_marker(
    body: str,
) -> tuple[str, str, str]:
    body = normalize_space(body)

    marker = WORK_MARKER_PATTERN.search(
        body
    )

    if marker is None:
        return (
            "",
            body,
            "NO_WORK_MARKER",
        )

    name = clean_name_candidate(
        body[: marker.start()]
    )

    description = normalize_space(
        body[marker.start():]
    )

    if not name:
        return (
            "",
            body,
            "EMPTY_NAME_BEFORE_MARKER",
        )

    return (
        name,
        description,
        "WORK_MARKER_SPLIT",
    )


def parse_address_line(
    value: str,
) -> dict:
    value = normalize_space(value)

    match = ADDRESS_PATTERN.match(
        value
    )

    if match is None:
        return {
            "city": None,
            "state": None,
            "license_number": None,
            "address_trailing_text": "",
            "address_parse_status": (
                "ADDRESS_PATTERN_NOT_MATCHED"
            ),
        }

    return {
        "city": normalize_space(
            match.group("city")
        ).upper(),
        "state": normalize_space(
            match.group("state")
        ).upper(),
        "license_number": normalize_license(
            match.group("license")
        ),
        "address_trailing_text": (
            normalize_space(
                match.group("trailing")
            )
        ),
        "address_parse_status": "PARSED",
    }


def extract_page_body_lines(
    raw_text: str,
    prime_bidder_id: str,
) -> list[str]:
    lines = [
        normalize_space(line)
        for line in (
            raw_text or ""
        ).splitlines()
    ]

    return [
        line
        for line in lines
        if line
        and normalize_vc_id(
            line[: len(prime_bidder_id) + 4]
        ).startswith(prime_bidder_id)
        or (
            line
            and ADDRESS_PATTERN.match(line)
        )
    ]


def collect_raw_rows(
    raw_pages: pd.DataFrame,
    linked_blocks: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict] = []

    page_lookup = {
        (
            str(row.contract_number),
            int(row.page_number),
        ): row.raw_page_text or ""
        for row in raw_pages.itertuples(
            index=False
        )
    }

    for block in linked_blocks.itertuples(
        index=False,
    ):
        contract_number = str(
            block.contract_number
        )

        prime_bidder_id = normalize_vc_id(
            block.bidder_id
        )

        disclosure_sequence = 0

        pending_disclosure: dict | None = None

        for page_number in range(
            int(block.first_page),
            int(block.last_page) + 1,
        ):
            raw_text = page_lookup.get(
                (
                    contract_number,
                    page_number,
                ),
                "",
            )

            lines = [
                normalize_space(line)
                for line in raw_text.splitlines()
                if normalize_space(line)
            ]

            for source_line_number, line in enumerate(
                lines,
                start=1,
            ):
                normalized_line = (
                    normalize_vc_id(
                        line[
                            : len(prime_bidder_id) + 4
                        ]
                    )
                )

                begins_disclosure = (
                    normalized_line.startswith(
                        prime_bidder_id
                    )
                    and line.upper().startswith(
                        prime_bidder_id
                    )
                )

                if begins_disclosure:
                    if pending_disclosure is not None:
                        pending_disclosure[
                            "row_parse_status"
                        ] = (
                            "REVIEW_REQUIRED_"
                            "MISSING_ADDRESS_LINE"
                        )

                        records.append(
                            pending_disclosure
                        )

                    disclosure_sequence += 1

                    body = normalize_space(
                        line[
                            len(prime_bidder_id):
                        ]
                    )

                    pending_disclosure = {
                        "contract_number": (
                            contract_number
                        ),
                        "district": (
                            int(block.district)
                            if hasattr(
                                block,
                                "district",
                            )
                            and pd.notna(
                                block.district
                            )
                            else None
                        ),
                        "bid_rank": int(
                            block.provisional_bid_rank
                        ),
                        "prime_bidder_id": (
                            prime_bidder_id
                        ),
                        "prime_bidder_name": (
                            None
                            if pd.isna(
                                block.bidder_name
                            )
                            else normalize_space(
                                block.bidder_name
                            )
                        ),
                        "bidder_block_number": int(
                            block.bidder_block_number
                        ),
                        "block_first_page": int(
                            block.first_page
                        ),
                        "block_last_page": int(
                            block.last_page
                        ),
                        "disclosure_sequence": (
                            disclosure_sequence
                        ),
                        "source_page_number": (
                            page_number
                        ),
                        "source_line_number": (
                            source_line_number
                        ),
                        "raw_disclosure_line": (
                            line
                        ),
                        "raw_disclosure_body": (
                            body
                        ),
                        "raw_address_line": None,
                        "city": None,
                        "state": None,
                        "license_number": None,
                        "address_trailing_text": "",
                        "subcontractor_name": None,
                        "work_description": None,
                        "item_reference": None,
                        "percentage": None,
                        "name_resolution_basis": None,
                        "address_parse_status": None,
                        "row_parse_status": (
                            "PENDING_ADDRESS"
                        ),
                    }

                    continue

                if pending_disclosure is None:
                    continue

                address_result = parse_address_line(
                    line
                )

                if (
                    address_result[
                        "address_parse_status"
                    ]
                    == "PARSED"
                ):
                    pending_disclosure[
                        "raw_address_line"
                    ] = line

                    pending_disclosure.update(
                        address_result
                    )

                    records.append(
                        pending_disclosure
                    )

                    pending_disclosure = None

                else:
                    pending_disclosure[
                        "raw_disclosure_body"
                    ] = normalize_space(
                        pending_disclosure[
                            "raw_disclosure_body"
                        ]
                        + " "
                        + line
                    )

        if pending_disclosure is not None:
            pending_disclosure[
                "row_parse_status"
            ] = (
                "REVIEW_REQUIRED_"
                "MISSING_ADDRESS_LINE"
            )

            records.append(
                pending_disclosure
            )

    return pd.DataFrame(
        records
    )


def build_license_name_lookup(
    frame: pd.DataFrame,
) -> dict[str, str]:
    lookup: dict[str, str] = {}

    usable = frame[
        frame["license_number"].notna()
        & ~frame[
            "license_number"
        ].isin(
            [
                "N/A",
                "NA",
                "ABSENT",
            ]
        )
    ]

    for license_number, group in usable.groupby(
        "license_number"
    ):
        bodies = (
            group["raw_disclosure_body"]
            .dropna()
            .astype(str)
            .tolist()
        )

        if len(bodies) < 2:
            continue

        prefix = clean_name_candidate(
            longest_common_token_prefix(
                bodies
            )
        )

        if len(prefix.split()) < 1:
            continue

        marker = WORK_MARKER_PATTERN.search(
            prefix
        )

        if marker is not None:
            prefix = clean_name_candidate(
                prefix[: marker.start()]
            )

        if prefix:
            lookup[
                str(license_number)
            ] = prefix

    return lookup


def finalize_rows(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    if frame.empty:
        return frame

    license_name_lookup = (
        build_license_name_lookup(
            frame
        )
    )

    finalized: list[dict] = []

    for row in frame.to_dict(
        orient="records"
    ):
        body = normalize_space(
            row["raw_disclosure_body"]
        )

        license_number = (
            None
            if pd.isna(
                row["license_number"]
            )
            else str(
                row["license_number"]
            )
        )

        resolved_name = (
            license_name_lookup.get(
                license_number or ""
            )
        )

        if resolved_name:
            subcontractor_name = (
                resolved_name
            )

            if body.upper().startswith(
                resolved_name.upper()
            ):
                work_description = (
                    normalize_space(
                        body[
                            len(resolved_name):
                        ]
                    )
                )
            else:
                _, work_description, _ = (
                    split_name_and_description_by_marker(
                        body
                    )
                )

            name_basis = (
                "LICENSE_REPEATED_PREFIX"
            )

        else:
            (
                subcontractor_name,
                work_description,
                name_basis,
            ) = (
                split_name_and_description_by_marker(
                    body
                )
            )

        trailing = normalize_space(
            row.get(
                "address_trailing_text",
                "",
            )
        )

        if trailing:
            work_description = normalize_space(
                (
                    work_description
                    or ""
                )
                + " "
                + trailing
            )

        item_match = ITEM_PATTERN.search(
            work_description or ""
        )

        percent_match = (
            PERCENT_PATTERN.search(
                work_description or ""
            )
        )

        item_reference = (
            normalize_space(
                item_match.group(1)
            )
            if item_match
            else None
        )

        percentage = (
            float(
                percent_match.group(1)
            )
            if percent_match
            else None
        )

        parse_issues: list[str] = []

        if not subcontractor_name:
            parse_issues.append(
                "SUBCONTRACTOR_NAME_UNRESOLVED"
            )

        if not row.get(
            "license_number"
        ):
            parse_issues.append(
                "LICENSE_UNRESOLVED"
            )

        if (
            row.get(
                "address_parse_status"
            )
            != "PARSED"
        ):
            parse_issues.append(
                "ADDRESS_UNRESOLVED"
            )

        row_status = (
            "READY_FOR_QA"
            if not parse_issues
            else (
                "REVIEW_REQUIRED_"
                + "|".join(parse_issues)
            )
        )

        row.update(
            {
                "subcontractor_name": (
                    subcontractor_name
                    or None
                ),
                "work_description": (
                    work_description
                    or None
                ),
                "item_reference": (
                    item_reference
                ),
                "percentage": (
                    percentage
                ),
                "name_resolution_basis": (
                    name_basis
                ),
                "row_parse_status": (
                    row_status
                ),
            }
        )

        finalized.append(
            row
        )

    result = pd.DataFrame(
        finalized
    )

    result.insert(
        0,
        "disclosure_id",
        [
            (
                f"{row.contract_number}|"
                f"{int(row.bid_rank):02d}|"
                f"{int(row.disclosure_sequence):04d}"
            )
            for row in result.itertuples(
                index=False
            )
        ],
    )

    return result


def run(
    config: PipelineConfig,
) -> int:
    logger, log_path = configure_logging(
        config.log_directory,
        "stage2_alternate_parser",
    )

    log_section(
        logger,
        "ALTERNATE-LAYOUT STAGE 2 PARSER",
        width=160,
    )

    linkage_path = (
        config.project_root
        / "data"
        / "reports"
        / "subcontractor"
        / (
            "alternate_layout_rank_linkage_"
            f"{config.target_year}.csv"
        )
    )

    if not linkage_path.exists():
        raise FileNotFoundError(
            f"Rank-linkage CSV not found: "
            f"{linkage_path}"
        )

    linked_blocks = pd.read_csv(
        linkage_path,
        dtype={
            "contract_number": str,
            "bidder_id": str,
        },
    )

    linked_blocks = linked_blocks[
        linked_blocks[
            "certification_status"
        ]
        == "READY_FOR_ALTERNATE_PARSE"
    ].copy()

    if linked_blocks.empty:
        raise RuntimeError(
            "No bidder blocks are ready "
            "for alternate parsing."
        )

    raw_pages_table = config.tables[
        "raw_pages"
    ]

    read_connection = connect_database(
        config.database_path,
        read_only=True,
    )

    require_objects(
        read_connection,
        [
            raw_pages_table,
            HISTORY_TABLE,
        ],
    )

    raw_q = quote_identifier(
        raw_pages_table
    )

    contract_values = (
        linked_blocks[
            "contract_number"
        ]
        .drop_duplicates()
        .tolist()
    )

    placeholders = ", ".join(
        ["?"] * len(contract_values)
    )

    raw_pages = read_connection.execute(
        f"""
        SELECT
            contract_number,
            page_number,
            raw_page_text

        FROM {raw_q}

        WHERE contract_number IN (
            {placeholders}
        )

        ORDER BY
            contract_number,
            page_number
        """,
        contract_values,
    ).fetchdf()

    read_connection.close()

    raw_rows = collect_raw_rows(
        raw_pages,
        linked_blocks,
    )

    parsed_rows = finalize_rows(
        raw_rows
    )

    if parsed_rows.empty:
        raise RuntimeError(
            "No disclosure rows were parsed."
        )

    duplicate_ids = int(
        parsed_rows[
            "disclosure_id"
        ].duplicated().sum()
    )

    missing_prime_context = int(
        (
            parsed_rows[
                "prime_bidder_id"
            ].isna()
            | parsed_rows[
                "bid_rank"
            ].isna()
        ).sum()
    )

    ready_rows = int(
        (
            parsed_rows[
                "row_parse_status"
            ] == "READY_FOR_QA"
        ).sum()
    )

    review_rows = int(
        len(parsed_rows)
        - ready_rows
    )

    report_directory = (
        config.project_root
        / "data"
        / "reports"
        / "subcontractor"
    )

    report_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    parsed_csv = (
        report_directory
        / (
            "alternate_layout_stage2_disclosures_"
            f"{config.target_year}.csv"
        )
    )

    review_csv = (
        report_directory
        / (
            "alternate_layout_stage2_review_"
            f"{config.target_year}.csv"
        )
    )

    parsed_rows.to_csv(
        parsed_csv,
        index=False,
    )

    parsed_rows[
        parsed_rows[
            "row_parse_status"
        ] != "READY_FOR_QA"
    ].to_csv(
        review_csv,
        index=False,
    )

    if duplicate_ids:
        raise RuntimeError(
            f"Duplicate disclosure IDs found: "
            f"{duplicate_ids:,}"
        )

    if missing_prime_context:
        raise RuntimeError(
            "Rows are missing prime bidder "
            "or bid-rank context."
        )

    backup_path = create_backup(
        config.database_path,
        config.backup_directory,
        "2025_alt_stage2_parser_v2",
    )

    write_connection = connect_database(
        config.database_path,
        read_only=False,
    )

    ensure_target_objects_absent(
        write_connection,
        [TARGET_TABLE],
    )

    write_connection.register(
        "alternate_stage2_frame",
        parsed_rows,
    )

    target_q = quote_identifier(
        TARGET_TABLE
    )

    write_connection.execute(
        f"""
        CREATE TABLE {target_q} AS

        SELECT *
        FROM alternate_stage2_frame
        """
    )

    inserted_rows = int(
        write_connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {target_q}
            """
        ).fetchone()[0]
    )

    inserted_contracts = int(
        write_connection.execute(
            f"""
            SELECT COUNT(
                DISTINCT contract_number
            )
            FROM {target_q}
            """
        ).fetchone()[0]
    )

    inserted_blocks = int(
        write_connection.execute(
            f"""
            SELECT COUNT(
                DISTINCT
                contract_number
                || '|'
                || CAST(
                    bidder_block_number
                    AS VARCHAR
                )
            )
            FROM {target_q}
            """
        ).fetchone()[0]
    )

    write_connection.unregister(
        "alternate_stage2_frame"
    )

    write_connection.close()

    log_key_value(
        logger,
        "Rank-linked contracts",
        linked_blocks[
            "contract_number"
        ].nunique(),
    )

    log_key_value(
        logger,
        "Rank-linked bidder blocks",
        len(linked_blocks),
    )

    log_key_value(
        logger,
        "Parsed disclosure rows",
        len(parsed_rows),
    )

    log_key_value(
        logger,
        "Rows ready for QA",
        ready_rows,
    )

    log_key_value(
        logger,
        "Rows requiring review",
        review_rows,
    )

    log_key_value(
        logger,
        "Duplicate disclosure IDs",
        duplicate_ids,
    )

    log_key_value(
        logger,
        "Inserted contracts",
        inserted_contracts,
    )

    log_key_value(
        logger,
        "Inserted bidder blocks",
        inserted_blocks,
    )

    log_key_value(
        logger,
        "Inserted table rows",
        inserted_rows,
    )

    log_key_value(
        logger,
        "Target table",
        TARGET_TABLE,
    )

    log_key_value(
        logger,
        "Backup",
        backup_path,
    )

    log_key_value(
        logger,
        "Parsed CSV",
        parsed_csv,
    )

    log_key_value(
        logger,
        "Review CSV",
        review_csv,
    )

    log_key_value(
        logger,
        "Log",
        log_path,
    )

    if inserted_rows != len(parsed_rows):
        logger.info("")
        logger.info(
            "ALTERNATE STAGE 2 PARSER FAILED"
        )

        return 1

    logger.info("")
    logger.info(
        "ALTERNATE STAGE 2 PARSER PASSED"
    )

    return 0


def main() -> int:
    config = PipelineConfig.load()
    config.ensure_directories()
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
