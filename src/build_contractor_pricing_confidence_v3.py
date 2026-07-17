from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_pricing_confidence_v3
        """)

        con.execute("""
        CREATE TABLE contractor_pricing_confidence_v3 AS

        SELECT

            contractor_id,

            item_code,

            item_description,

            unit,

            bid_count AS observations,

            median_unit_price AS contractor_median_price,


            CASE

                WHEN bid_count >= 50
                THEN 'HIGH'

                WHEN bid_count >= 15
                THEN 'MEDIUM'

                ELSE 'LOW'

            END AS confidence_level,


            CASE

                WHEN bid_count >= 50
                THEN 1.00

                WHEN bid_count >= 15
                THEN 0.75

                ELSE 0.50

            END AS confidence_factor


        FROM contractor_item_price_history_v3

        """)

    print("Contractor pricing confidence v3 created.")


if __name__ == "__main__":
    main()
