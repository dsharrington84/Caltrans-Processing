from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_item_price_stability
        """)

        con.execute("""
        CREATE TABLE contractor_item_price_stability AS

        SELECT

            contractor_id,

            item_code,

            item_description,

            unit,

            bid_count AS observations,

            median_unit_price AS median_price,

            min_unit_price,

            max_unit_price,


            ROUND(
                (
                    max_unit_price
                    -
                    min_unit_price
                )
                /
                NULLIF(
                    median_unit_price,
                    0
                )
                * 100,

                2

            ) AS price_spread_pct,


            CASE

                WHEN

                (
                    max_unit_price
                    -
                    min_unit_price
                )
                /
                NULLIF(
                    median_unit_price,
                    0
                )
                * 100 < 50

                THEN 'STABLE'


                WHEN

                (
                    max_unit_price
                    -
                    min_unit_price
                )
                /
                NULLIF(
                    median_unit_price,
                    0
                )
                * 100 <= 150

                THEN 'MODERATE'


                ELSE 'VARIABLE'

            END AS stability_class


        FROM contractor_item_price_history_v3

        """)

    print("Contractor item price stability created.")


if __name__ == "__main__":
    main()
