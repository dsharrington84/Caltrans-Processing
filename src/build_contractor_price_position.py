from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_price_position
        """)

        con.execute("""
        CREATE TABLE contractor_price_position AS

        SELECT

            c.contractor_id,

            c.item_code,

            c.item_description,

            c.unit,

            c.bid_count,

            c.median_unit_price AS contractor_median_price,

            m.observations AS market_observations,

            m.median_unit_price AS market_median_price,

            ROUND(
                (
                    c.median_unit_price
                    -
                    m.median_unit_price
                )
                /
                NULLIF(
                    m.median_unit_price,
                    0
                )
                * 100,
                2
            ) AS variance_pct,


            CASE

                WHEN c.median_unit_price
                    <
                    m.median_unit_price * 0.90
                THEN 'BELOW MARKET'

                WHEN c.median_unit_price
                    >
                    m.median_unit_price * 1.10
                THEN 'ABOVE MARKET'

                ELSE 'MARKET RANGE'

            END AS market_position


        FROM contractor_item_price_history c

        JOIN item_market_bands m

            ON c.item_code = m.item_code

            AND c.unit = m.unit


        """)

    print("Contractor pricing position created.")


if __name__ == "__main__":
    main()
