from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path


APP_HOME = Path.home() / "caltrans-processing"
DATA = APP_HOME / "data"

COMMANDS = {
    "Tesseract": "tesseract",
    "OCRmyPDF": "ocrmypdf",
    "Poppler pdftotext": "pdftotext",
    "MuPDF": "mutool",
    "LibreOffice": "libreoffice",
    "SQLite": "sqlite3",
    "Git": "git",
}

MODULES = {
    "DuckDB": "duckdb",
    "pandas": "pandas",
    "Polars": "polars",
    "openpyxl": "openpyxl",
    "PyMuPDF": "fitz",
    "pdfplumber": "pdfplumber",
    "Camelot": "camelot",
    "PyArrow": "pyarrow",
}


def check_command(label: str, command: str) -> tuple[bool, str]:
    path = shutil.which(command)
    if not path:
        return False, "not found"
    result = subprocess.run(
        [command, "--version"], capture_output=True, text=True, timeout=15
    )
    first_line = (result.stdout or result.stderr).splitlines()
    return True, first_line[0].strip() if first_line else path


def main() -> None:
    failures = 0
    print(f"Python: {sys.version.split()[0]}")

    for label, command in COMMANDS.items():
        ok, detail = check_command(label, command)
        print(f"[{'OK' if ok else 'FAIL'}] {label}: {detail}")
        failures += int(not ok)

    for label, module in MODULES.items():
        try:
            imported = importlib.import_module(module)
            version = getattr(imported, "__version__", "installed")
            print(f"[OK] {label}: {version}")
        except Exception as exc:
            print(f"[FAIL] {label}: {exc}")
            failures += 1

    if DATA.exists() and DATA.is_dir():
        print(f"[OK] Windows data folder: {DATA.resolve()}")
    else:
        print(f"[FAIL] Windows data folder link: {DATA}")
        failures += 1

    database = DATA / "database" / "caltrans_pricing.duckdb"
    if database.exists():
        print(f"[OK] DuckDB database: {database}")
    else:
        print(f"[FAIL] DuckDB database missing: {database}")
        failures += 1

    if failures:
        raise SystemExit(f"Environment verification failed with {failures} issue(s).")
    print("Environment verification passed.")


if __name__ == "__main__":
    main()
