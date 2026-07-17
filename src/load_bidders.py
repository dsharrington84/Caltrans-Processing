from pathlib import Path
import duckdb
import pandas as pd


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"

BIDDER_FILE = (
    APP_HOME
    / "data/05_Working/bidder_extract/"
    / "batch_a_complete/bidders.csv"
)


def main():

    print("Loading:")
    print(BIDDER_FILE)

    df = pd.read_csv(
        BIDDER_FILE,
        dtype=str
    )

    print(f"Bidder records: {len(df)}")

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS bidder_staging
        """)

        con.execute("""
        CREATE TABLE bidder_staging (
            contract_number VARCHAR,
            bid_rank INTEGER,
            roster_bid_amount DECIMAL(18,2),
            bidder_id VARCHAR,
            bidder_name VARCHAR,
            award_status VARCHAR
        )
        """)

        con.register("bidder_df", df)

        con.execute("""
        INSERT INTO bidder_staging
        SELECT
            contract_number,
            CAST(bid_rank AS INTEGER),
            CAST(roster_bid_amount AS DECIMAL(18,2)),
            bidder_id,
            bidder_name,
            award_status
        FROM bidder_df
        """)

    print("Bidder staging loaded.")


if __name__ == "__main__":
    main()
