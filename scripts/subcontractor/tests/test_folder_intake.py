from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.subcontractor.intake_folder import (
    build_records,
    extract_contract_number,
)


def main() -> int:
    assert (
        extract_contract_number(
            "07-4V5004.pdf"
        )
        == "07-4V5004"
    )

    assert (
        extract_contract_number(
            "08-1J65U4 (1).PDF"
        )
        == "08-1J65U4"
    )

    assert (
        extract_contract_number(
            "not-a-contract.pdf"
        )
        == ""
    )

    with TemporaryDirectory() as temp:
        folder = Path(temp)

        files = (
            "07-4V5004.pdf",
            "08-1P2804.pdf",
            "12-0K0244.pdf",
            "12-0K0244 (1).pdf",
            "unknown.pdf",
        )

        for filename in files:
            (
                folder
                / filename
            ).write_bytes(
                b"%PDF-1.4\n"
            )

        records = build_records(
            folder=folder,
            current_contracts={
                "07-4V5004",
            },
            normalized_contracts={
                "07-4V5004",
                "08-1P2804",
            },
            promoted_contracts=set(),
            recursive=False,
            include_hashes=False,
        )

        by_filename = {
            record.filename: record
            for record in records
        }

        assert (
            by_filename[
                "07-4V5004.pdf"
            ].pipeline_status
            == "CURRENT"
        )

        assert (
            by_filename[
                "08-1P2804.pdf"
            ].pipeline_status
            == "NORMALIZED_NOT_CURRENT"
        )

        assert (
            by_filename[
                "12-0K0244.pdf"
            ].pipeline_status
            == "READY_FOR_PARSE"
        )

        assert (
            by_filename[
                "12-0K0244 (1).pdf"
            ].pipeline_status
            == "DUPLICATE_FILE"
        )

        assert (
            by_filename[
                "12-0K0244 (1).pdf"
            ].underlying_status
            == "READY_FOR_PARSE"
        )

        assert (
            by_filename[
                "unknown.pdf"
            ].pipeline_status
            == "INVALID_FILENAME"
        )

    print()
    print("FOLDER INTAKE TEST PASSED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
