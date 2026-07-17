from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS district_adjustment_reliability
        """)


        con.execute("""
        CREATE TABLE district_adjustment_reliability AS


        SELECT

            district,

            item_code,

            item_description,

            unit,


            observations,

            contractor_count,


            district_median_price,

            statewide_median_price,

            adjustment_pct,


            CASE

                WHEN observations >= 50

                THEN 'HIGH'


                WHEN observations >= 25

                THEN 'MEDIUM'


                ELSE 'LOW'


            END AS observation_confidence,


            CASE

                WHEN observations >= 25
                     AND ABS(adjustment_pct) <= 25

                THEN 'HIGH'


                WHEN observations >= 10

                THEN 'MEDIUM'


                ELSE 'LOW'


            END AS reliability_class,


            CASE

                WHEN observations >= 25
                     AND ABS(adjustment_pct) <= 25

                THEN 1.00


                WHEN observations >= 10

                THEN 0.75


                ELSE 0.25


            END AS adjustment_factor


        FROM district_item_market_bands

        """)


    print("District adjustment reliability created.")


if __name__ == "__main__":
    main()
