from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_market_trend_reliability
        """)

        con.execute("""
        CREATE TABLE item_market_trend_reliability AS

        SELECT

            s.item_code,

            s.item_description,

            s.unit,

            s.latest_year,

            s.prior_year,

            s.prior_year_price,

            s.latest_year_price,

            s.change_pct,

            s.trend_signal,

            s.latest_observations,


            CASE

                WHEN s.latest_observations >= 100
                THEN 'HIGH'

                WHEN s.latest_observations >= 25
                THEN 'MEDIUM'

                ELSE 'LOW'

            END AS observation_confidence,


            CASE

                WHEN s.latest_observations >= 100
                     AND ABS(s.change_pct) <= 25

                THEN 'HIGH'


                WHEN s.latest_observations >= 25

                THEN 'MEDIUM'


                ELSE 'LOW'


            END AS trend_reliability,


            CASE

                WHEN s.latest_observations >= 100
                     AND ABS(s.change_pct) <= 25

                THEN 1.00


                WHEN s.latest_observations >= 25

                THEN 0.75


                ELSE 0.50


            END AS trend_factor


        FROM item_market_trend_signals s

        """)

    print("Item market trend reliability created.")


if __name__ == "__main__":
    main()
