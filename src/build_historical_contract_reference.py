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


def load_contracts():

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
                sheet_name="Contracts"
            )

            df["source_batch"] = zip_file.stem

            frames.append(df)

        shutil.rmtree(temp)

    return pd.concat(
        frames,
        ignore_index=True
    )


def main():

    print("Loading historical contracts...")

    contracts = load_contracts()

    print(
        "Raw records:",
        len(contracts)
    )


    contracts = contracts.drop_duplicates(
        subset=["contract_number"]
    )

    print(
        "Unique contracts:",
        len(contracts)
    )


    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS historical_contract_reference
        """)

        con.register(
            "contracts_df",
            contracts
        )

        con.execute("""
        CREATE TABLE historical_contract_reference AS
        SELECT *
        FROM contracts_df
        """)

    print(
        "Historical contract reference created."
    )


if __name__ == "__main__":
    main()
