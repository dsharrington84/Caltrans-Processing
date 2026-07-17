from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_weighted_market_price
        """)

        con.execute("""
        CREATE TABLE item_weighted_market_price AS

        SELECT

            item_code,
            item_description,
            unit,

            observations,
            contractor_count,
            contract_count,

            low_bid_median,
            top3_median,
            all_bid_median,

            ROUND(

                (
                    COALESCE(low_bid_median, all_bid_median)
                    * 0.50
                )

                +

                (
                    COALESCE(top3_median, all_bid_median)
                    * 0.30
                )

                +

                (
                    all_bid_median
                    * 0.20
                ),

            2) AS weighted_market_price,


            confidence_level


        FROM item_market_bands_v2

        """)

    print("Weighted market price created.")


if __name__ == "__main__":
    main()
