from pathlib import Path
import duckdb
import pandas as pd


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"

MASTER = (
    APP_HOME
    / "data/03_Processed/Caltrans_Pricing_Data_Baseline_2026-07-11/"
    / "LIVE_BASELINE/02_Master_Bid_Tab_Data/"
    / "Caltrans_Master_All_Contracts_v4.xlsx"
)


def main():

    print("Loading:")
    print(MASTER)

    df = pd.read_excel(
        MASTER,
        sheet_name="Contracts",
        dtype={"contract_number": str},
    )

    print(f"Contracts found: {len(df)}")

    with duckdb.connect(str(DB_PATH)) as con:

        for _, row in df.iterrows():

            con.execute(
                """
                INSERT OR REPLACE INTO contracts
                (
                    contract_number,
                    bid_open_date,
                    source_file_id
                )
                VALUES (?, ?, ?)
                """,
                [
                    row["contract_number"],
                    pd.to_datetime(row["bid_opening_date"]).date(),
                    row["source_file"],
                ],
            )

    print("Baseline contracts loaded.")


if __name__ == "__main__":
    main()
