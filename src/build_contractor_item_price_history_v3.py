from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_item_price_history_v3
        """)

        con.execute("""
        CREATE TABLE contractor_item_price_history_v3 AS

        SELECT

            COALESCE(
                m.canonical_contractor_id,
                h.contractor_id
            ) AS contractor_id,

            h.item_code,

            h.item_description,

            h.unit,


            COUNT(*) AS bid_count,


            ROUND(
                AVG(h.unit_price),
                2
            ) AS avg_unit_price,


            ROUND(
                MEDIAN(h.unit_price),
                2
            ) AS median_unit_price,


            MIN(h.unit_price)
                AS min_unit_price,


            MAX(h.unit_price)
                AS max_unit_price


        FROM historical_bid_prices h


        LEFT JOIN contractor_id_merge_map m

            ON h.contractor_id = m.old_contractor_id


        WHERE h.unit_price IS NOT NULL


        GROUP BY

            COALESCE(
                m.canonical_contractor_id,
                h.contractor_id
            ),

            h.item_code,

            h.item_description,

            h.unit

        """)

    print("Contractor item price history v3 created.")


if __name__ == "__main__":
    main()
