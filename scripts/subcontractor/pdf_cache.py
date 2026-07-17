from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable


def normalize_contract_directory(
    contract_number: str,
) -> str:
    return contract_number.strip().upper()


def contract_cache_directory(
    cache_root: Path,
    target_year: int,
    contract_number: str,
) -> Path:
    return (
        cache_root
        / str(target_year)
        / normalize_contract_directory(
            contract_number
        )
    )


def page_cache_path(
    cache_root: Path,
    target_year: int,
    contract_number: str,
    page_number: int,
) -> Path:
    if page_number <= 0:
        raise ValueError(
            "Page numbers must be positive."
        )

    return (
        contract_cache_directory(
            cache_root,
            target_year,
            contract_number,
        )
        / f"page_{page_number:04d}.txt"
    )


def text_sha256(
    text: str,
) -> str:
    return hashlib.sha256(
        text.encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()


def extract_pdf_page(
    pdf_path: Path,
    page_number: int,
) -> str:
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    if page_number <= 0:
        raise ValueError(
            "Page numbers must be positive."
        )

    result = subprocess.run(
        [
            "pdftotext",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-layout",
            str(pdf_path),
            "-",
        ],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "pdftotext failed for "
            f"{pdf_path}, page {page_number}: "
            f"{result.stderr.strip()}"
        )

    return result.stdout or ""


def write_cached_page(
    cache_root: Path,
    target_year: int,
    contract_number: str,
    page_number: int,
    text: str,
) -> Path:
    path = page_cache_path(
        cache_root,
        target_year,
        contract_number,
        page_number,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        text,
        encoding="utf-8",
    )

    return path


def read_cached_page(
    cache_root: Path,
    target_year: int,
    contract_number: str,
    page_number: int,
) -> str | None:
    path = page_cache_path(
        cache_root,
        target_year,
        contract_number,
        page_number,
    )

    if not path.exists():
        return None

    return path.read_text(
        encoding="utf-8",
    )


def get_or_extract_page(
    cache_root: Path,
    target_year: int,
    contract_number: str,
    pdf_path: Path,
    page_number: int,
    *,
    refresh: bool = False,
) -> tuple[str, Path, bool]:
    if not refresh:
        cached_text = read_cached_page(
            cache_root,
            target_year,
            contract_number,
            page_number,
        )

        if cached_text is not None:
            return (
                cached_text,
                page_cache_path(
                    cache_root,
                    target_year,
                    contract_number,
                    page_number,
                ),
                True,
            )

    text = extract_pdf_page(
        pdf_path,
        page_number,
    )

    cache_path = write_cached_page(
        cache_root,
        target_year,
        contract_number,
        page_number,
        text,
    )

    return (
        text,
        cache_path,
        False,
    )


def write_contract_manifest(
    cache_root: Path,
    target_year: int,
    contract_number: str,
    page_records: Iterable[dict],
) -> Path:
    directory = contract_cache_directory(
        cache_root,
        target_year,
        contract_number,
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    records = list(
        page_records
    )

    manifest_path = (
        directory
        / "cache_manifest.json"
    )

    payload = {
        "contract_number": (
            contract_number
        ),
        "target_year": target_year,
        "generated_at": (
            datetime.now().isoformat()
        ),
        "page_count": len(records),
        "pages": records,
    }

    manifest_path.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    return manifest_path


def validate_cached_page(
    cache_root: Path,
    target_year: int,
    contract_number: str,
    page_number: int,
    expected_hash: str | None = None,
) -> dict:
    path = page_cache_path(
        cache_root,
        target_year,
        contract_number,
        page_number,
    )

    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "sha256": None,
            "hash_match": False,
            "text_characters": 0,
        }

    text = path.read_text(
        encoding="utf-8",
    )

    calculated_hash = text_sha256(
        text
    )

    return {
        "exists": True,
        "path": str(path),
        "sha256": calculated_hash,
        "hash_match": (
            calculated_hash == expected_hash
            if expected_hash
            else True
        ),
        "text_characters": len(text),
    }
