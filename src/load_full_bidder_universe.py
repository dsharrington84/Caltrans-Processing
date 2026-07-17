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

BATCH_A = (
    APP_HOME
    / "data/03_Processed/Caltrans_Pricing_Data_Baseline_2026-07-11/"
    / "SOURCE_ARCHIVE/03_Initial_Controlled_Parse/"
    / "Caltrans_Batch_A_All_Bidder_Extract_Package.zip"
)


def load_batch_a():

    temp = Path(tempfile.mkdtemp())

    rows = []

    with zipfile.ZipFile(BATCH_A) as z:
        z.extractall(temp)

    bidder_file = list(temp.rglob("bidders.csv"))[0]

    df = pd.read_csv(bidder_file)

    df["batch_source"] = "Batch_A"

    rows.append(df)

    shutil.rmtree(temp)

    return rows


def load_processed_batches():

    rows = []

    for zip_file in sorted(ARCHIVE_DIR.glob("Caltrans_Batch_*_Processed_Package.zip")):

        temp = Path(tempfile.mkdtemp())

        with zipfile.ZipFile(zip_file) as z:
            z.extractall(temp)

        bidder_files = list(
            temp.rglob("*Controlled_Parse_Results.xlsx")
        )

        if bidder_files:

            df = pd.read_excel(
                bidder_files[0],
                sheet_name="Bidders"
            )

            df["batch_source"] = zip_file.stem

            rows.append(df)

        shutil.rmtree(temp)

    return rows


def main():

    frames = []

    frames.extend(load_batch_a())

    frames.extend(load_processed_batches())

    bidders = pd.concat(
        frames,
        ignore_index=True
    )

    bidders = bidders.drop_duplicates(
        subset=[
            "contract_number",
            "bid_rank",
            "bidder_id"
        ]
    )

    print(f"Total bidder records: {len(bidders)}")

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS bidder_staging
        """)

        con.register(
            "bidder_df",
            bidders
        )

        con.execute("""
        CREATE TABLE bidder_staging AS
        SELECT *
        FROM bidder_df
        """)

    print("Full bidder universe loaded.")


if __name__ == "__main__":
    main()
