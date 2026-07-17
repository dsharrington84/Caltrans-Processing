from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        UPDATE historical_bid_prices
        SET contractor_id = m.contractor_id
        FROM contractor_bidder_mapping m
        WHERE historical_bid_prices.bidder_id = m.bidder_id
        """)

    print("Historical bid prices linked to contractors.")


if __name__ == "__main__":
    main()
