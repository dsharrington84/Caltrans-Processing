from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_market_trend_signals
        """)


        con.execute("""
        CREATE TABLE item_market_trend_signals AS


        WITH yearly AS (

            SELECT

                item_code,

                item_description,

                unit,

                bid_year,

                median_price,

                observations,


                ROW_NUMBER() OVER (

                    PARTITION BY
                        item_code,
                        item_description,
                        unit

                    ORDER BY
                        bid_year DESC

                ) AS rn


            FROM item_market_trends_v2

        ),


        latest AS (

            SELECT *

            FROM yearly

            WHERE rn = 1

        ),


        prior AS (

            SELECT *

            FROM yearly

            WHERE rn = 2

        )


        SELECT

            l.item_code,

            l.item_description,

            l.unit,


            l.bid_year AS latest_year,

            p.bid_year AS prior_year,


            p.median_price AS prior_year_price,

            l.median_price AS latest_year_price,


            ROUND(

                (

                    l.median_price
                    -
                    p.median_price

                )
                /
                NULLIF(
                    p.median_price,
                    0
                )
                * 100,

                2

            ) AS change_pct,


            CASE

                WHEN

                    (
                    (
                    l.median_price
                    -
                    p.median_price
                    )
                    /
                    NULLIF(
                        p.median_price,
                        0
                    )
                    * 100
                    )

                    > 5

                THEN 'INCREASING'


                WHEN

                    (
                    (
                    l.median_price
                    -
                    p.median_price
                    )
                    /
                    NULLIF(
                        p.median_price,
                        0
                    )
                    * 100
                    )

                    < -5

                THEN 'DECREASING'


                ELSE 'STABLE'


            END AS trend_signal,


            CASE

                WHEN l.observations >= 100
                THEN 'HIGH'

                WHEN l.observations >= 25
                THEN 'MEDIUM'

                ELSE 'LOW'

            END AS confidence_level,


            l.observations AS latest_observations


        FROM latest l


        JOIN prior p

            ON l.item_code = p.item_code

            AND l.item_description =
                p.item_description

            AND l.unit = p.unit

        """)


    print("Item market trend signals created.")


if __name__ == "__main__":
    main()
