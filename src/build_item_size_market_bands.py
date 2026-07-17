from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_size_market_bands
        """)


        con.execute("""
        CREATE TABLE item_size_market_bands AS


        SELECT

            p.project_size_band,

            h.item_code,

            h.item_description,

            h.unit,


            COUNT(*) AS observations,


            COUNT(DISTINCT h.contract_number)
                AS contract_count,


            COUNT(DISTINCT h.contractor_id)
                AS contractor_count,


            ROUND(
                MEDIAN(h.unit_price),
                2
            ) AS median_unit_price,


            ROUND(
                AVG(h.unit_price),
                2
            ) AS average_unit_price,


            MIN(h.unit_price)
                AS min_unit_price,


            MAX(h.unit_price)
                AS max_unit_price


        FROM historical_bid_prices h


        JOIN project_size_bands p

            ON h.contract_number =
               p.contract_number


        WHERE h.unit_price IS NOT NULL


        GROUP BY

            p.project_size_band,

            h.item_code,

            h.item_description,

            h.unit

        """)


    print("Item size market bands created.")


if __name__ == "__main__":
    main()
