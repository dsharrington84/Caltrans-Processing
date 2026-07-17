from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_code_crosswalk
        """)

        con.execute("""
        CREATE TABLE item_code_crosswalk AS

        SELECT

            b.item_code,

            b.item_description,

            b.unit,


            COUNT(DISTINCT b.contract_number)
                AS bid_item_contracts,


            CASE
                WHEN p.item_code IS NOT NULL
                THEN TRUE
                ELSE FALSE
            END AS price_history_exists,


            CASE
                WHEN m.item_code IS NOT NULL
                THEN TRUE
                ELSE FALSE
            END AS market_band_exists


        FROM bid_item_reference b


        LEFT JOIN (
            SELECT DISTINCT
                item_code,
                item_description,
                unit
            FROM historical_bid_prices
        ) p

            ON b.item_code = p.item_code
            AND b.item_description = p.item_description
            AND b.unit = p.unit


        LEFT JOIN (
            SELECT DISTINCT
                item_code,
                item_description,
                unit
            FROM item_market_bands_v2
        ) m

            ON b.item_code = m.item_code
            AND b.item_description = m.item_description
            AND b.unit = m.unit


        GROUP BY

            b.item_code,
            b.item_description,
            b.unit,
            p.item_code,
            m.item_code

        """)

    print("Item code crosswalk created.")


if __name__ == "__main__":
    main()
