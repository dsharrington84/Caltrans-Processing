from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS winning_vs_market_bands
        """)


        con.execute("""
        CREATE TABLE winning_vs_market_bands AS


        SELECT

            item_code,

            item_description,

            unit,


            observations,

            contractor_count,

            contract_count,


            low_bid_median
                AS winning_market_price,


            top3_median
                AS competitive_market_price,


            all_bid_median
                AS full_market_price,


            ROUND(

                (
                    top3_median
                    -
                    low_bid_median
                )

                /

                NULLIF(
                    low_bid_median,
                    0
                )

                * 100,

                2

            ) AS winning_to_competitive_pct,


            ROUND(

                (
                    all_bid_median
                    -
                    top3_median
                )

                /

                NULLIF(
                    top3_median,
                    0
                )

                * 100,

                2

            ) AS competitive_to_full_pct,


            confidence_level


        FROM item_market_bands_v2

        """)


    print("Winning vs market bands created.")


if __name__ == "__main__":
    main()
