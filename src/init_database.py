from __future__ import annotations

from pathlib import Path

import duckdb


APP_HOME = Path.home() / "caltrans-processing"
DATA = APP_HOME / "data"
DB_DIR = DATA / "database"
DB_PATH = DB_DIR / "caltrans_pricing.duckdb"


DDL = """
CREATE TABLE IF NOT EXISTS source_files (
    source_file_id VARCHAR PRIMARY KEY,
    contract_number VARCHAR,
    document_type VARCHAR NOT NULL,
    original_filename VARCHAR NOT NULL,
    relative_path VARCHAR NOT NULL,
    sha256 VARCHAR,
    file_size_bytes BIGINT,
    modified_at TIMESTAMP,
    processing_status VARCHAR DEFAULT 'pending',
    batch_number INTEGER,
    notes VARCHAR
);

CREATE TABLE IF NOT EXISTS contracts (
    contract_number VARCHAR PRIMARY KEY,
    district VARCHAR,
    county VARCHAR,
    route VARCHAR,
    location_description VARCHAR,
    project_description VARCHAR,
    bid_open_date DATE,
    engineers_estimate DECIMAL(18,2),
    awarded_contractor_id VARCHAR,
    awarded_amount DECIMAL(18,2),
    source_file_id VARCHAR,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS contractors (
    contractor_id VARCHAR PRIMARY KEY,
    canonical_name VARCHAR NOT NULL,
    license_number VARCHAR,
    normalized_name VARCHAR,
    is_sema BOOLEAN DEFAULT FALSE,
    notes VARCHAR
);

CREATE TABLE IF NOT EXISTS contractor_aliases (
    alias_name VARCHAR PRIMARY KEY,
    contractor_id VARCHAR NOT NULL,
    source VARCHAR,
    confidence DOUBLE
);

CREATE TABLE IF NOT EXISTS bids (
    contract_number VARCHAR NOT NULL,
    contractor_id VARCHAR NOT NULL,
    bid_rank INTEGER,
    bid_total DECIMAL(18,2),
    responsive BOOLEAN,
    source_file_id VARCHAR,
    PRIMARY KEY (contract_number, contractor_id)
);

CREATE TABLE IF NOT EXISTS bid_items (
    contract_number VARCHAR NOT NULL,
    contractor_id VARCHAR NOT NULL,
    item_number VARCHAR NOT NULL,
    item_code VARCHAR,
    description VARCHAR,
    unit VARCHAR,
    quantity DOUBLE,
    unit_price DECIMAL(18,4),
    extension DECIMAL(18,2),
    source_file_id VARCHAR,
    parse_confidence DOUBLE,
    review_status VARCHAR DEFAULT 'unreviewed',
    PRIMARY KEY (contract_number, contractor_id, item_number)
);

CREATE TABLE IF NOT EXISTS processing_runs (
    run_id VARCHAR PRIMARY KEY,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    batch_number INTEGER,
    files_attempted INTEGER,
    files_succeeded INTEGER,
    files_failed INTEGER,
    application_version VARCHAR,
    notes VARCHAR
);

CREATE TABLE IF NOT EXISTS processing_exceptions (
    exception_id VARCHAR PRIMARY KEY,
    run_id VARCHAR,
    source_file_id VARCHAR,
    severity VARCHAR,
    exception_type VARCHAR,
    message VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp,
    resolved_at TIMESTAMP,
    resolution_notes VARCHAR
);
"""


def main() -> None:
    if not DATA.exists():
        raise SystemExit(f"Data link is missing: {DATA}")
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as connection:
        connection.execute(DDL)
        table_count = connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='main'"
        ).fetchone()[0]
    print(f"Database ready: {DB_PATH}")
    print(f"Tables available: {table_count}")


if __name__ == "__main__":
    main()
