from pathlib import Path
import duckdb


APP_HOME = Path.home() / "caltrans-processing"

DB_PATH = APP_HOME / "data/database/caltrans_pricing.duckdb"


def main():

    with duckdb.connect(str(DB_PATH)) as con:

        con.execute("""
        DROP TABLE IF EXISTS item_market_depth_score
        """)


        con.execute("""
        CREATE TABLE item_market_depth_score AS


        WITH year_depth AS (

            SELECT

                item_code,

                item_description,

                unit,

                COUNT(DISTINCT bid_year)
                    AS years_available


            FROM item_market_trends_v2


            GROUP BY

                item_code,

                item_description,

                unit

        )


        SELECT

            m.item_code,

            m.item_description,

            m.unit,


            m.observations,


            m.contractor_count,


            m.contract_count,


            y.years_available,


            (

                CASE

                    WHEN m.observations >= 500
                    THEN 40

                    WHEN m.observations >= 100
                    THEN 30

                    WHEN m.observations >= 25
                    THEN 20

                    ELSE 10

                END


                +

                CASE

                    WHEN m.contractor_count >= 100
                    THEN 30

                    WHEN m.contractor_count >= 25
                    THEN 20

                    ELSE 10

                END


                +

                CASE

                    WHEN m.contract_count >= 50
                    THEN 20

                    WHEN m.contract_count >= 10
                    THEN 15

                    ELSE 5

                END


                +

                CASE

                    WHEN y.years_available >= 4
                    THEN 10

                    WHEN y.years_available >= 2
                    THEN 5

                    ELSE 0

                END

            ) AS market_depth_score


        FROM item_market_bands_v2 m


        LEFT JOIN year_depth y

            ON m.item_code = y.item_code

            AND m.item_description =
                y.item_description

            AND m.unit = y.unit

        """)


    print("Item market depth score created.")


if __name__ == "__main__":
    main()
