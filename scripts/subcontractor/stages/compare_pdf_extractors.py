from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import fitz


def clean_text(
    value: str,
) -> str:
    value = value.replace(
        "\x00",
        "",
    )

    return "\n".join(
        line.rstrip()
        for line in value.splitlines()
    ).strip()


def quality_score(
    value: str,
) -> dict:
    printable = sum(
        character.isprintable()
        or character in "\n\t"
        for character in value
    )

    alpha = sum(
        character.isalpha()
        for character in value
    )

    replacement = value.count(
        "\ufffd"
    )

    suspicious = len(
        re.findall(
            r"[ÿ␦]",
            value,
        )
    )

    total = max(
        len(value),
        1,
    )

    return {
        "characters": len(value),
        "printable_ratio": (
            printable / total
        ),
        "alpha_ratio": (
            alpha / total
        ),
        "replacement_chars": (
            replacement
        ),
        "suspicious_chars": (
            suspicious
        ),
        "score": (
            printable / total * 100
            + alpha / total * 50
            - replacement * 5
            - suspicious * 2
        ),
    }


def pdftotext_extract(
    pdf_path: Path,
    page_number: int,
    mode: str,
) -> str:
    command = [
        "pdftotext",
        "-f",
        str(page_number),
        "-l",
        str(page_number),
    ]

    if mode:
        command.append(
            f"-{mode}"
        )

    command.extend(
        [
            str(pdf_path),
            "-",
        ]
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
        )

    return clean_text(
        result.stdout
    )


def pymupdf_extract(
    pdf_path: Path,
    page_number: int,
) -> str:
    document = fitz.open(
        pdf_path
    )

    try:
        if page_number < 1:
            raise ValueError(
                "Page number must be positive."
            )

        if page_number > document.page_count:
            raise ValueError(
                f"PDF has only "
                f"{document.page_count} pages."
            )

        page = document.load_page(
            page_number - 1
        )

        return clean_text(
            page.get_text(
                "text",
                sort=True,
            )
        )

    finally:
        document.close()


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--pdf",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--page",
        required=True,
        type=int,
    )

    arguments = parser.parse_args()

    methods = {
        "PDFTOTEXT_LAYOUT": (
            lambda: pdftotext_extract(
                arguments.pdf,
                arguments.page,
                "layout",
            )
        ),
        "PDFTOTEXT_RAW": (
            lambda: pdftotext_extract(
                arguments.pdf,
                arguments.page,
                "raw",
            )
        ),
        "PYMUPDF": (
            lambda: pymupdf_extract(
                arguments.pdf,
                arguments.page,
            )
        ),
    }

    results: list[tuple] = []

    for method_name, extractor in methods.items():
        try:
            text = extractor()
            metrics = quality_score(
                text
            )

            results.append(
                (
                    method_name,
                    text,
                    metrics,
                )
            )

        except Exception as error:
            results.append(
                (
                    method_name,
                    "",
                    {
                        "score": float("-inf"),
                        "error": str(error),
                    },
                )
            )

    results.sort(
        key=lambda result: (
            result[2]["score"]
        ),
        reverse=True,
    )

    print()
    print("PDF EXTRACTOR COMPARISON")
    print("=" * 160)
    print(f"PDF: {arguments.pdf}")
    print(f"Page: {arguments.page}")

    for method_name, text, metrics in results:
        print()
        print(method_name)
        print("-" * 160)
        print(metrics)

        if text:
            print()
            print(text[:5000])
        else:
            print(
                metrics.get(
                    "error",
                    "No text returned.",
                )
            )

    print()
    print(
        f"BEST METHOD: "
        f"{results[0][0]}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
