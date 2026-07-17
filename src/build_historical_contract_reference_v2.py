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


def load_source_manifests():

    frames = []

    for zip_file in sorted(
        ARCHIVE_DIR.glob("Caltrans_Batch_*_Processed_Package.zip")
    ):

        temp_dir = Path(tempfile.mkdtemp())

        try:

            with zipfile.ZipFile(zip_file) as z:
                z.extractall(temp_dir)

            manifest_files = list(
                temp_dir.rglob("source_manifest.csv")
            )

            for file in manifest_files:

                df = pd.read_csv(file)

                df["source_batch"] = zip_file.stem

                frames.append(df)

        finally:

            shutil.rmtree(temp_dir)


    if frames:

        return pd.concat(
            frames,
            ignore_index=True
        )

    return pd.DataFrame()



def build_district_lookup(manifests):

    # Keep only usable district records
    manifests = manifests[
        manifests["district"].notna()
    ].copy()


    # Normalize district format
    manifests["district"] = (
        manifests["district"]
        .astype(str)
        .str.strip()
    )


    # One district per contract
    district_lookup = (

        manifests[[
            "contract_number",
            "district"
        ]]

        .drop_duplicates()

        .groupby(
            "contract_number",
            as_index=False
        )

        .agg(
            {
                "district": "first"
            }
        )
    )


    return district_lookup



def main():

    with duckdb.connect(str(DB_PATH)) as con:


        manifests = load_source_manifests()


        print(
            "Raw manifest records:",
            len(manifests)
        )


        district_lookup = build_district_lookup(
            manifests
        )


        print(
            "Unique district contracts:",
            len(district_lookup)
        )


        con.register(
            "district_lookup_df",
            district_lookup
        )


        con.execute("""
        DROP TABLE IF EXISTS contract_district_reference
        """)


        con.execute("""
        CREATE TABLE contract_district_reference AS

        SELECT *

        FROM district_lookup_df

        """)


        con.execute("""
        DROP TABLE IF EXISTS historical_contract_reference_v2
        """)


        con.execute("""
        CREATE TABLE historical_contract_reference_v2 AS


        SELECT

            h.contract_number,

            h.bid_opening_date,

            d.district,


            h.declared_items,

            h.declared_bidders,

            h.source_file,

            h.low_bidder_name


        FROM historical_contract_reference h


        LEFT JOIN contract_district_reference d

            ON h.contract_number =
               d.contract_number

        """)


    print(
        "Historical contract reference v2 created."
    )


if __name__ == "__main__":
    main()
