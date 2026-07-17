from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_item_price_history
        """)

        con.execute("""
        CREATE TABLE contractor_item_price_history AS

        SELECT
            contractor_id,
            item_code,
            item_description,
            unit,

            COUNT(*) AS bid_count,

            ROUND(AVG(unit_price), 2) AS avg_unit_price,

            ROUND(
                MEDIAN(unit_price),
                2
            ) AS median_unit_price,

            MIN(unit_price) AS min_unit_price,

            MAX(unit_price) AS max_unit_price

        FROM historical_bid_prices

        WHERE unit_price IS NOT NULL

        GROUP BY
            contractor_id,
            item_code,
            item_description,
            unit

        """)

    print("Contractor item price history created.")


if __name__ == "__main__":
    main()
