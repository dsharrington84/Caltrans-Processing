from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS pricing_adjustment_guardrails
        """)


        con.execute("""
        CREATE TABLE pricing_adjustment_guardrails AS


        WITH contractor_summary AS (

            SELECT

                item_code,

                item_description,

                unit,


                AVG(

                    CASE

                        WHEN pricing_signal =
                            'STRONG_CONTRACTOR_SIGNAL'

                        THEN 1.00


                        WHEN pricing_signal =
                            'MODERATE_CONTRACTOR_SIGNAL'

                        THEN 0.50


                        ELSE 0


                    END

                ) AS contractor_influence_factor


            FROM contractor_price_position_v4


            GROUP BY

                item_code,

                item_description,

                unit

        ),


        district_summary AS (

            SELECT

                item_code,

                item_description,

                unit,


                AVG(

                    adjustment_pct
                    *
                    adjustment_factor

                ) AS weighted_district_adjustment


            FROM district_adjustment_reliability


            GROUP BY

                item_code,

                item_description,

                unit

        )


        SELECT


            p.item_code,

            p.item_description,

            p.unit,


            p.weighted_market_price,


            t.change_pct,


            CASE

                WHEN t.change_pct > 15

                THEN 15


                WHEN t.change_pct < -15

                THEN -15


                ELSE COALESCE(
                    t.change_pct,
                    0
                )


            END AS capped_trend_pct,


            COALESCE(
                d.weighted_district_adjustment,
                0
            ) AS weighted_district_adjustment,


            COALESCE(
                c.contractor_influence_factor,
                0
            ) AS contractor_influence_factor


        FROM item_pricing_bands_final p


        LEFT JOIN item_market_trend_reliability t

            ON p.item_code = t.item_code

            AND p.item_description =
                t.item_description

            AND p.unit = t.unit


        LEFT JOIN district_summary d

            ON p.item_code = d.item_code

            AND p.item_description =
                d.item_description

            AND p.unit = d.unit


        LEFT JOIN contractor_summary c

            ON p.item_code = c.item_code

            AND p.item_description =
                c.item_description

            AND p.unit = c.unit

        """)


    print("Pricing adjustment guardrails created.")


if __name__ == "__main__":
    main()
