from pathlib import Path
import duckdb
import pandas as pd
import zipfile
import tempfile
import shutil


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"

ARCHIVE_DIR = (
    APP_HOME
    / "data/03_Processed/Caltrans_Pricing_Data_Baseline_2026-07-11/"
    / "SOURCE_ARCHIVE/02_Processed_Batch_Packages"
)


def load_bid_prices():

    frames = []

    for zip_file in sorted(
        ARCHIVE_DIR.glob("Caltrans_Batch_*_Processed_Package.zip")
    ):

        temp = Path(tempfile.mkdtemp())

        with zipfile.ZipFile(zip_file) as z:
            z.extractall(temp)

        files = list(
            temp.rglob("*Controlled_Parse_Results.xlsx")
        )

        if files:

            df = pd.read_excel(
                files[0],
                sheet_name="Bid Prices"
            )

            df["source_batch"] = zip_file.stem

            frames.append(df)

        shutil.rmtree(temp)

    return pd.concat(
        frames,
        ignore_index=True
    )


def main():

    print("Loading bid price history...")

    prices = load_bid_prices()

    print(
        f"Bid price records found: {len(prices)}"
    )

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS historical_bid_prices
        """)

        con.execute("""
        CREATE TABLE historical_bid_prices AS

        SELECT
            p.contract_number,
            p.bidder_id,
            p.bidder_name,
            c.contractor_id,

            p.bid_rank,

            p.item_number,
            p.item_code,
            p.item_description,
            p.unit,

            p.estimated_quantity,

            p.unit_price,
            p.extended_amount,

            p.source_batch

        FROM prices p

        LEFT JOIN contractors c
            ON p.bidder_id = c.contractor_id

        """)

    print(
        "Historical bid price table created."
    )


if __name__ == "__main__":
    main()
