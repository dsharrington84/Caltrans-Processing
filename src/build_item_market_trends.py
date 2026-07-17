from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_market_trends
        """)


        con.execute("""
        CREATE TABLE item_market_trends AS


        SELECT

            h.item_code,

            h.item_description,

            h.unit,


            YEAR(c.bid_open_date)
                AS bid_year,


            COUNT(*) AS observations,


            ROUND(
                MEDIAN(h.unit_price),
                2
            ) AS median_price,


            ROUND(
                AVG(h.unit_price),
                2
            ) AS average_price,


            MIN(h.unit_price)
                AS min_price,


            MAX(h.unit_price)
                AS max_price


        FROM historical_bid_prices h


        JOIN contracts c

            ON h.contract_number =
               c.contract_number


        WHERE h.unit_price IS NOT NULL


        GROUP BY

            h.item_code,

            h.item_description,

            h.unit,

            YEAR(c.bid_open_date)

        """)


    print("Item market trends created.")


if __name__ == "__main__":
    main()
