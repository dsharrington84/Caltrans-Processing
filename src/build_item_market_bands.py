from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_market_bands
        """)

        con.execute("""
        CREATE TABLE item_market_bands AS

        SELECT

            item_code,
            item_description,
            unit,

            COUNT(*) AS observations,

            ROUND(
                AVG(unit_price),
                2
            ) AS avg_unit_price,

            ROUND(
                MEDIAN(unit_price),
                2
            ) AS median_unit_price,

            ROUND(
                QUANTILE_CONT(unit_price, 0.25),
                2
            ) AS p25_unit_price,

            ROUND(
                QUANTILE_CONT(unit_price, 0.75),
                2
            ) AS p75_unit_price,

            MIN(unit_price) AS min_unit_price,

            MAX(unit_price) AS max_unit_price


        FROM historical_bid_prices

        WHERE unit_price IS NOT NULL

        GROUP BY
            item_code,
            item_description,
            unit

        """)

    print("Item market bands created.")


if __name__ == "__main__":
    main()
