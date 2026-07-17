from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS contractor_price_position_v4
        """)

        con.execute("""
        CREATE TABLE contractor_price_position_v4 AS

        SELECT

            h.contractor_id,

            h.item_code,

            h.item_description,

            h.unit,


            h.bid_count AS observations,


            h.median_unit_price
                AS contractor_median_price,


            m.weighted_market_price,


            ROUND(
                (
                    h.median_unit_price
                    -
                    m.weighted_market_price
                )
                /
                NULLIF(
                    m.weighted_market_price,
                    0
                )
                * 100,

                2

            ) AS variance_pct,


            c.confidence_score,

            c.confidence_level,


            s.stability_class,

            s.price_spread_pct,


            CASE

                WHEN
                    c.confidence_level = 'HIGH'
                    AND
                    s.stability_class = 'STABLE'

                THEN 'STRONG_CONTRACTOR_SIGNAL'


                WHEN
                    c.confidence_level IN ('HIGH','MEDIUM')
                    AND
                    s.stability_class <> 'VARIABLE'

                THEN 'MODERATE_CONTRACTOR_SIGNAL'


                ELSE 'MARKET_DRIVEN'


            END AS pricing_signal


        FROM contractor_item_price_history_v3 h


        JOIN item_weighted_market_price m

            ON h.item_code = m.item_code

            AND h.item_description = m.item_description

            AND h.unit = m.unit


        JOIN contractor_pricing_confidence_v4 c

            ON h.contractor_id = c.contractor_id

            AND h.item_code = c.item_code

            AND h.item_description = c.item_description

            AND h.unit = c.unit


        JOIN contractor_item_price_stability s

            ON h.contractor_id = s.contractor_id

            AND h.item_code = s.item_code

            AND h.item_description = s.item_description

            AND h.unit = s.unit


        """)

    print("Contractor price position v4 created.")


if __name__ == "__main__":
    main()
